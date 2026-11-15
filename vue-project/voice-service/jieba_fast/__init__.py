"""jieba_fast 的兼容层（仓库自带，无需编译）。

背景：GPT-SoVITS 的 `GPT_SoVITS/text/tone_sandhi.py`、`text/chinese.py`、
`text/chinese2.py` 都 `import jieba_fast`。但 `jieba_fast` 在 PyPI 上只有源码包
（0.53 的 sdist），Windows 上安装需要 MSVC 编译器，绝大多数环境装不上。

本包放在 `voice-service/` 下，`api_v2.py` 被拉起时脚本目录（也就是
`voice-service/`）会自动进入 `sys.path`，因此 `import jieba_fast` 命中这里，
全部转发到纯 Python 的 `jieba`（`requirements-min.txt` 里已有）。

速度会略慢于 C 版本，对本项目的短句合成没有可感知影响。
"""

import jieba as _jieba
import jieba.posseg as posseg

from jieba import *  # noqa: F401,F403

cut = _jieba.cut
lcut = _jieba.lcut
cut_for_search = _jieba.cut_for_search
lcut_for_search = _jieba.lcut_for_search
Tokenizer = _jieba.Tokenizer
setLogLevel = _jieba.setLogLevel
initialize = _jieba.initialize
dt = getattr(_jieba, "dt", None)

__version__ = getattr(_jieba, "__version__", "0.42.1")


def __getattr__(name):
    return getattr(_jieba, name)
