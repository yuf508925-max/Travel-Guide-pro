# =====================================================================
# routers/music.py —— 右上角「音乐」：上传 / 列表 / 删除 / 播放
# ---------------------------------------------------------------------
#   需求：名字和「记忆」中间加一个音乐入口，可以上传自己的音乐，
#        支持播放/暂停、上一首/下一首、拖进度；
#        文件只放在本机临时目录（不进云端），退出登录清空；
#        数据库里记好每一首的位置，会话被删时音乐一起删。
#
#   接口：
#     GET    /api/music                 我这次登录上传的音乐（按顺序）
#     POST   /api/music/upload?name=..  上传（请求体直接是文件字节）
#     DELETE /api/music/{id}            删一首（文件一起删）
#     GET    /api/music/{id}/file       取音频流（支持 Range，拖进度条要用）
#
#   为什么不用 multipart/form-data：
#     那需要额外装 python-multipart，这里直接吃 request.body()，
#     前端 fetch(url, { method:'POST', body: file }) 就够了，少一个依赖。
# =====================================================================

import mimetypes

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import StreamingResponse

from .. import music_store
from ..db import db
from .auth import current_user

router = APIRouter(prefix="/api/music", tags=["music"])

CHUNK = 64 * 1024


def _token(request: Request) -> str:
    """当前这次登录的 token（音乐按会话隔离）"""
    token = request.cookies.get("fufu_session")
    if not token:
        raise HTTPException(401, "请先登录")
    return token


def _row_to_dict(row) -> dict:
    return {
        "id": row["id"],
        "name": row["name"],
        "ext": row["ext"],
        "size": row["size"],
        "position": row["position"],
        "created_at": row["created_at"],
        "url": f"/api/music/{row['id']}/file",
    }


def _owned_track(conn, track_id: int, token: str):
    row = conn.execute(
        "SELECT * FROM music_tracks WHERE id = ? AND session_token = ?",
        (track_id, token),
    ).fetchone()
    if row is None:
        raise HTTPException(404, "这首音乐不在了")
    return row


@router.get("")
def list_music(request: Request):
    user = current_user(request)
    token = _token(request)
    with db() as conn:
        rows = conn.execute(
            """SELECT id, name, ext, size, position, created_at
                 FROM music_tracks
                WHERE session_token = ? AND user_id = ?
                ORDER BY position, id""",
            (token, user["id"]),
        ).fetchall()
    return {"tracks": [_row_to_dict(r) for r in rows]}


@router.post("/upload")
async def upload_music(
    request: Request,
    name: str = Query("", max_length=200),
):
    """请求体就是音频字节；文件名用 ?name= 传（前端 encodeURIComponent 过）"""
    user = current_user(request)
    token = _token(request)

    data = await request.body()
    if not data:
        raise HTTPException(400, "没收到文件内容")

    filename = (name or "").strip() or "music.mp3"
    if not music_store.is_allowed(filename):
        raise HTTPException(
            400,
            "只支持 mp3 / wav / ogg / m4a / aac / flac / opus / webm 这些格式",
        )
    if len(data) > music_store.MAX_BYTES:
        raise HTTPException(
            413,
            f"文件太大了，单首上限 {music_store.MAX_BYTES // (1024 * 1024)}MB",
        )

    stored, size = music_store.save_bytes(token, filename, data)
    display = filename.rsplit("/", 1)[-1].rsplit("\\", 1)[-1][:120]

    with db() as conn:
        next_pos = conn.execute(
            "SELECT COALESCE(MAX(position), 0) + 1 AS p FROM music_tracks WHERE session_token = ?",
            (token,),
        ).fetchone()["p"]
        cur = conn.execute(
            """INSERT INTO music_tracks
                    (user_id, session_token, name, filename, ext, size, position)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                user["id"],
                token,
                display,
                stored,
                music_store.ext_of(filename),
                size,
                next_pos,
            ),
        )
        row = conn.execute(
            "SELECT * FROM music_tracks WHERE id = ?", (cur.lastrowid,)
        ).fetchone()
    return _row_to_dict(row)


@router.delete("/{track_id}")
def delete_music(track_id: int, request: Request):
    token = _token(request)
    with db() as conn:
        row = _owned_track(conn, track_id, token)
        conn.execute("DELETE FROM music_tracks WHERE id = ?", (track_id,))
        # 删完把后面的顺序补上，列表里不留空号
        conn.execute(
            "UPDATE music_tracks SET position = position - 1 WHERE session_token = ? AND position > ?",
            (token, row["position"]),
        )
    path = music_store.file_path(row["session_token"], row["filename"])
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass
    return {"ok": True}


@router.get("/{track_id}/file")
def stream_music(track_id: int, request: Request):
    """音频流：支持 Range（浏览器拖进度条、直接跳到中间都要它）"""
    token = _token(request)
    with db() as conn:
        row = _owned_track(conn, track_id, token)

    path = music_store.file_path(row["session_token"], row["filename"])
    if not path.is_file():
        raise HTTPException(404, "文件已经不在了，重新上传一次吧")

    total = path.stat().st_size
    media_type = mimetypes.guess_type(row["filename"])[0] or "audio/mpeg"

    start, end = 0, total - 1
    status = 200

    range_header = request.headers.get("range")
    if range_header and range_header.lower().startswith("bytes="):
        raw = range_header.split("=", 1)[1].split(",")[0].strip()
        first, _, second = raw.partition("-")
        try:
            if first:
                start = int(first)
                end = int(second) if second else total - 1
            elif second:                     # bytes=-500，要最后 500 字节
                start = max(0, total - int(second))
                end = total - 1
        except ValueError:
            start, end = 0, total - 1

        end = min(end, total - 1)
        if start > end or start >= total:
            raise HTTPException(
                416,
                "请求的区间不合法",
                headers={"Content-Range": f"bytes */{total}"},
            )
        status = 206

    length = end - start + 1

    def body():
        with path.open("rb") as fh:
            fh.seek(start)
            remain = length
            while remain > 0:
                chunk = fh.read(min(CHUNK, remain))
                if not chunk:
                    break
                remain -= len(chunk)
                yield chunk

    headers = {
        "Accept-Ranges": "bytes",
        "Content-Length": str(length),
        "Cache-Control": "no-store",
    }
    if status == 206:
        headers["Content-Range"] = f"bytes {start}-{end}/{total}"

    return StreamingResponse(body(), status_code=status, headers=headers, media_type=media_type)
