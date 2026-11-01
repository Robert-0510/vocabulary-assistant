# 第三方组件与许可

本项目以 MIT 许可证发布（见 [LICENSE](LICENSE)）。运行或构建本项目会使用以下第三方组件，
它们分别遵循各自的许可证。发布二进制或源码时请保留本文件以及各组件自带的许可证文本。

版本号以 `backend/requirements.lock.txt` 与 `frontend/package-lock.json` 为准。

## 后端（Python）

| 组件 | 许可证 | 项目主页 |
|------|--------|----------|
| FastAPI | MIT | https://github.com/fastapi/fastapi |
| Uvicorn | BSD-3-Clause | https://github.com/encode/uvicorn |
| SQLAlchemy | MIT | https://github.com/sqlalchemy/sqlalchemy |
| PyMySQL | MIT | https://github.com/PyMySQL/PyMySQL |
| cryptography | Apache-2.0 / BSD-3-Clause | https://github.com/pyca/cryptography |
| python-multipart | Apache-2.0 | https://github.com/Kludex/python-multipart |
| Pydantic / pydantic-settings | MIT | https://github.com/pydantic/pydantic |
| FSRS (`fsrs`) | MIT | https://github.com/open-spaced-repetition/py-fsrs |
| pytest / httpx（开发依赖） | MIT / BSD-3-Clause | https://github.com/pytest-dev/pytest / https://github.com/encode/httpx |
| PyInstaller（构建依赖） | GPL-2.0-or-later WITH Bootloader-exception | https://github.com/pyinstaller/pyinstaller |

> PyInstaller 的 bootloader 例外允许将打包产物按你自己的许可证分发；打包生成的 exe
> 不受 GPL 传染。详情见 PyInstaller 的 `COPYING` 文件。

## 前端（JavaScript / TypeScript）

| 组件 | 许可证 | 项目主页 |
|------|--------|----------|
| Vue 3 | MIT | https://github.com/vuejs/core |
| Vue Router | MIT | https://github.com/vuejs/router |
| Pinia | MIT | https://github.com/vuejs/pinia |
| Element Plus | MIT | https://github.com/element-plus/element-plus |
| @element-plus/icons-vue | MIT | https://github.com/element-plus/element-plus-icons |
| Axios | MIT | https://github.com/axios/axios |
| Apache ECharts | Apache-2.0 | https://github.com/apache/echarts |
| Vite | MIT | https://github.com/vitejs/vite |
| TypeScript | Apache-2.0 | https://github.com/microsoft/TypeScript |
| vue-tsc | MIT | https://github.com/vuejs/language-tools |

## Apache ECharts NOTICE

```
Apache ECharts
Copyright 2017-2024 The Apache Software Foundation

This product includes software developed at
The Apache Software Foundation (https://www.apache.org/).
```

完整的 Apache-2.0 与 BSD-3-Clause 许可证文本见 [LICENSES/](LICENSES/)。

## 数据与内容

- 仓库中的 `sample/示例词书.md` 为项目自编示例，随 MIT 许可证提供。
- 本项目不再分发任何第三方备考资料。用户自行导入的词书内容由用户自行负责其版权与使用权。
- 发音功能可能调用浏览器 Web Speech API 或 `dict.youdao.com` 的公开语音接口；
  这些服务由第三方提供，不在本项目许可证覆盖范围内。

如发现遗漏的第三方组件或许可问题，请通过仓库 Issue 联系维护者。
