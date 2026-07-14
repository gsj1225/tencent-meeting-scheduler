# 腾讯会议排课调度工具

适用于小团队的本地排课工具。每位使用者在自己的 Windows 电脑上运行程序并维护独立的 SQLite 数据库，同时通过同一企业授权同步腾讯会议中进行中或待开始的有效会议。

## 数据模型

- 源码通过私有 GitHub 仓库共享。
- `schedule_data.db` 只保存在各自电脑，不提交到 GitHub。
- 腾讯会议 API 凭据保存在各自电脑的 Windows 用户环境变量中，不提交到 GitHub。
- 腾讯会议同步可以让不同电脑看到同一企业的有效会议，但本地新增且未创建腾讯会议的排课不会自动共享。

## Windows 安装

1. 安装 Python 3.11 或更高版本，安装时勾选 `Add Python to PATH`。
2. 克隆私有仓库或下载并解压 ZIP。
3. 在项目文件夹打开 PowerShell，安装依赖：

   ```powershell
   python -m pip install -r requirements.txt
   ```

4. 双击 `配置腾讯会议API.bat`，依次填写 AppId、SdkId、SecretId 和 SecretKey。
5. 输入 SecretKey 后按 Enter，确认出现 `Configuration saved successfully`。
6. 双击 `启动服务.bat`，浏览器会自动打开。

## 日常使用

- 启动：双击 `启动服务.bat`。
- 停止：双击 `停止服务.bat`。
- 备份：复制本机的 `schedule_data.db` 到安全位置。
- 更新代码：停止服务后执行 `git pull`，再重新启动。

## 多人使用注意

- 所有人配置同一企业的腾讯会议 API 后，可以同步同一批腾讯会议。
- 每台电脑的本地排课、备注和导入数据相互独立，不会经由 GitHub 自动合并。
- 两个人同时创建或修改同一场会议可能产生重复或覆盖，建议约定谁负责创建和删除会议。
- GitHub 只用来分发程序更新，不用来同步运行中的数据库。

## 安全说明

- 不要提交 `schedule_data.db`、备份文件或真实 API 凭据。
- 不要通过聊天、截图或 GitHub Issue 发送 SecretId/SecretKey。
- 曾经暴露过的 SecretId/SecretKey 必须在腾讯会议后台轮换。
- 私有仓库只邀请得到企业授权的同事。
