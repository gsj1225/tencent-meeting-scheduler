# 腾讯会议排课调度工具

这是一个供小团队使用的 Windows/macOS 本地排课工具。每位同事从私有 GitHub 仓库下载同一套程序，在自己的电脑上运行，并使用自己的本地数据库；所有人配置同一企业的腾讯会议 API 后，可以同步同一企业中的腾讯会议。

## 先了解工作方式

- GitHub 用来分发程序和后续更新，不用来同步排课数据库。
- 每台电脑都会生成自己的 `schedule_data.db`，彼此独立。
- 腾讯会议中已经创建的会议可以通过“同步腾讯会议”拉取到各自电脑。
- 本地备注、导入数据以及尚未创建腾讯会议的内容不会自动分享给其他人。
- 每个腾讯会议账号可以绑定一个 Edge 浏览器配置文件，点击“去排课”时会用对应的登录状态打开腾讯会议后台。
- 所有电脑共用同一企业 API 的调用额度，请避免频繁重复同步或重复创建会议。

## 一、管理员先邀请同事

这是私有仓库，同事必须先获得访问权限，否则会看到 404 或无权访问。

1. 管理员打开仓库：<https://github.com/gsj1225/tencent-meeting-scheduler>
2. 进入 `Settings` → `Collaborators`。
3. 点击 `Add people`，填写同事的 GitHub 用户名或邮箱。
4. 同事登录自己的 GitHub 账号并接受邀请。

## 二、同事电脑需要准备的环境

支持 Windows 10、Windows 11 和较新版本的 macOS。

需要安装：

1. **Git**：用于克隆和更新项目。
2. **Python 3.11 或更高版本**：Windows 安装时必须勾选 `Add Python to PATH`。
3. **Microsoft Edge**：用于按不同账号的登录状态打开腾讯会议后台。

### Windows 一次安装所需环境

Windows 10/11 打开 PowerShell，依次执行：

```powershell
winget install --id Git.Git -e --source winget --accept-package-agreements --accept-source-agreements
winget install --id Python.Python.3.11 -e --source winget --accept-package-agreements --accept-source-agreements
winget install --id Microsoft.Edge -e --source winget --accept-package-agreements --accept-source-agreements
```

安装完成后关闭并重新打开 PowerShell。如果系统提示找不到 `winget`，请先在 Microsoft Store 安装或更新“应用安装程序（App Installer）”。Windows 通常已经自带 Edge，重复执行 Edge 安装命令不会影响已有配置。

### macOS 一次安装所需环境

Mac 打开“终端”。如果没有 Homebrew，先执行 Homebrew 官方安装命令：

```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

安装结束后，按照终端最后显示的提示把 Homebrew 加入 PATH，或者关闭并重新打开终端。然后执行：

```bash
brew install git python3
brew install --cask microsoft-edge
```

如果已经安装了其中某个软件，Homebrew 会保留现有安装或提示已经安装。

Windows 打开 PowerShell 检查：

```powershell
git --version
python --version
```

两条命令都能显示版本号，才说明环境已经可用。

Mac 打开“终端”检查：

```bash
git --version
python3 --version
```

如果 Mac 第一次执行 `git` 时提示安装 Command Line Tools，按照系统提示完成安装即可。

## 三、从 GitHub 下载项目

### 方法 A：使用 GitHub Desktop（推荐给不熟悉命令行的同事）

1. 安装并登录 GitHub Desktop。
2. 点击 `File` → `Clone repository`。
3. 在仓库列表中选择 `gsj1225/tencent-meeting-scheduler`。
4. 选择本机保存位置，然后点击 `Clone`。
5. 在 GitHub Desktop 中点击 `Repository` → `Show in Explorer/Finder` 打开项目文件夹。

### 方法 B：使用命令行

Windows 打开 PowerShell，Mac 打开“终端”，执行：

```bash
git clone https://github.com/gsj1225/tencent-meeting-scheduler.git
cd tencent-meeting-scheduler
```

如果提示登录，请使用已经接受仓库邀请的 GitHub 账号完成浏览器授权。GitHub 账号密码不能直接作为 Git 命令行密码使用。

## 四、首次安装 Python 依赖

### Windows

在项目文件夹空白处按住 `Shift` 并点击鼠标右键，选择“在终端中打开”，然后执行：

```powershell
python -m pip install -r requirements.txt
```

看到安装成功后即可关闭终端。每台电脑首次下载时执行一次即可；以后如果 `requirements.txt` 有更新，再重新执行一次。

如果提示找不到 `python`，请重新安装 Python 并勾选 `Add Python to PATH`，然后关闭并重新打开 PowerShell。

### macOS

推荐双击 `install_mac.command`。它会在项目目录创建独立的 `.venv` 环境并自动安装依赖。

也可以在项目目录的终端中执行：

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
```

如果第一次双击 `.command` 文件时被 macOS 阻止，请按住 `Control` 点击文件，选择“打开”，再确认一次。也可以在终端执行：

```bash
chmod +x *.command
```

## 五、配置腾讯会议 API

每台电脑都要单独配置一次。API 凭据不会保存在 GitHub 项目或本地数据库中。

Windows 双击 `配置腾讯会议API.bat`；Mac 双击 `configure_api.command`。

1. 按顺序输入：
   - `AppId`：企业 ID，通常是较短的纯数字。
   - `SdkId`：腾讯会议自建应用的 SDK ID，通常是较长的纯数字。
   - `SecretId`：自建应用的 SecretId。
   - `SecretKey`：自建应用的 SecretKey。输入时窗口不会显示字符，这是正常现象。
2. 输入 SecretKey 后按一次 `Enter`。
3. 必须看到 `Configuration saved successfully.` 才算配置完成。
4. 如果服务已经运行，先停止服务，再重新启动。

Windows 凭据保存在当前 Windows 用户环境变量中；Mac 凭据保存在用户目录的 `~/.tencent-meeting-scheduler.env`，文件权限会自动限制为仅当前用户可读写。

如果出现 `AppId and SdkId appear to be reversed`，说明两个数字可能填反了。不要把 SecretId、SecretKey 发到群聊、GitHub Issue 或截图中。

## 六、启动和停止

### Windows 启动和停止

双击 `启动服务.bat`。

- 程序会自动寻找 `8080` 到 `8099` 之间的可用端口。
- 浏览器通常会自动打开，例如 `http://localhost:8080`。
- 如果 8080 已被占用，程序会自动使用 8081、8082 等端口。
- 启动窗口需要保持打开；关闭窗口会停止当前服务。

双击 `停止服务.bat`。脚本只会停止本工具识别到的服务，不会随意结束其他占用端口的程序。

### macOS 启动和停止

- 启动：双击 `start_service.command`。
- 停止：双击 `stop_service.command`。
- 启动脚本会优先使用项目里的 `.venv`，并自动读取 Mac 用户目录中保存的 API 配置。
- 启动终端窗口需要保持打开；关闭窗口会停止当前服务。

两个系统都会自动寻找 `8080` 到 `8099` 之间的可用端口，并自动打开浏览器。服务只监听本机地址，不需要也不应该把局域网地址发给其他同事。

## 七、首次同步腾讯会议

1. 启动服务并进入工具首页。
2. 点击右上角“同步腾讯会议”。
3. 等待同步完成。
4. 打开“日期总览”或“排课记录”，确认会议已经出现。

首次同步后，本机才会拥有对应的本地排课记录。其他同事在自己的电脑上也需要单独点击同步。

## 八、配置 Edge 多账号排课

如果需要点击某个账号后直接打开它对应的腾讯会议登录状态，请为每个账号准备独立的 Edge 配置文件。

### 1. 在 Edge 中创建并登录不同配置

1. 打开 Microsoft Edge。
2. 点击右上角头像，选择“添加配置文件”。
3. 每个腾讯会议账号使用一个独立的 Edge 配置文件。
4. 在各自配置文件中打开腾讯会议官网并登录对应账号。
5. 不要退出登录，也不要清除该配置文件的 Cookie。

### 2. 找到 Edge 配置名称

在目标 Edge 配置文件中，在地址栏输入：

```text
edge://version
```

找到“配置文件路径”或 `Profile path`。只记录路径最后一段，例如：

```text
Default
Profile 1
Profile 2
```

这里需要填写的是文件夹名称，不是 Edge 右上角显示的中文昵称。

### 3. 在工具中绑定

1. 打开“账号管理”。
2. 在账号右侧的“Edge配置”中填写 `Default`、`Profile 1` 等名称。
3. 点击“保存”。
4. 点击“去排课”测试是否打开了正确的 Edge 登录账号。

## 九、日常排课流程

1. 在“排课”页面填写日期、起止时间和会议主题。
2. 查找空闲账号并选择一个账号。
3. 点击“确认排课”或账号旁边的“去排课”。
4. 工具会使用该账号绑定的 Edge 配置打开腾讯会议用户中心。
5. 在腾讯会议页面中手动创建会议。
6. 创建完成后回到工具，点击“同步腾讯会议”。
7. 同步成功后，会议会进入本机排课记录。

两个人不要同时创建或删除同一场会议，否则可能产生重复会议或数据不一致。建议团队约定会议创建和删除的负责人。

## 十、更新到最新版本

更新前先停止服务：Windows 双击 `停止服务.bat`，Mac 双击 `stop_service.command`，然后使用以下任一种方法。

### GitHub Desktop

1. 打开对应仓库。
2. 点击 `Fetch origin`。
3. 如果出现 `Pull origin`，继续点击拉取。
4. Windows 重新双击 `启动服务.bat`；Mac 重新双击 `start_service.command`。

### 命令行

在项目文件夹中打开 PowerShell 或终端：

```bash
git pull
```

Windows 如依赖有变化，再执行：

```powershell
python -m pip install -r requirements.txt
```

Mac 如依赖有变化，重新双击 `install_mac.command`。然后重新启动服务。

正常更新不会删除本机的 `schedule_data.db`，但重要数据仍建议定期备份。

## 十一、本地数据和备份

- 主数据库：`schedule_data.db`
- 数据库只保存在当前电脑，不会提交到 GitHub。
- 备份方法：停止服务后，把 `schedule_data.db` 复制到安全位置。
- 不要把一个正在使用的数据库同时放到多人共享网盘中运行。
- 更换电脑时，可以在停止服务后复制旧电脑的 `schedule_data.db` 到新电脑的项目目录。

## 十二、常见问题

### 克隆时提示 404 或没有权限

确认管理员已经邀请你的 GitHub 账号，并且你已经接受邀请；同时确认 GitHub Desktop 或浏览器登录的是被邀请的账号。

### Windows 提示 `python` 不是内部或外部命令

重新安装 Python，并勾选 `Add Python to PATH`。安装后关闭所有 PowerShell 窗口再重新打开。

### 提示缺少 `requests`

在项目目录执行：

```powershell
python -m pip install -r requirements.txt
```

Mac 重新双击 `install_mac.command`。

### 同步失败，使用本地数据

依次检查：

1. 网络是否正常。
2. Windows 是否完整执行了 `配置腾讯会议API.bat`，或 Mac 是否完整执行了 `configure_api.command`。
3. 是否看到 `Configuration saved successfully.`。
4. AppId 和 SdkId 是否填反。
5. SecretId、SecretKey 是否有效或已经在后台被重置。
6. 配置后是否停止并重新启动了服务。

### 点击“去排课”打开了错误账号

在正确的 Edge 配置中打开 `edge://version`，重新确认 `Profile path` 的最后一段，并在“账号管理”中修改后保存。

### 8080 端口被占用

不需要手动处理。启动脚本会自动选择 8081 到 8099 中的空闲端口。浏览器打开的实际地址以启动窗口显示为准。

### Windows 双击启动后窗口立即关闭

在项目文件夹中打开 PowerShell，执行：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\start_server.ps1
```

保留窗口并把最后一段错误信息发给管理员。发送截图前必须遮挡所有 API 凭据。

### Mac 双击 `.command` 文件提示没有权限

在项目文件夹的终端中执行：

```bash
chmod +x *.command
```

然后按住 `Control` 点击需要运行的 `.command` 文件，选择“打开”。

### Mac 启动后没有自动打开页面

保留启动终端窗口，根据窗口显示的端口手动访问 `http://localhost:8080`；如果 8080 被占用，端口可能是 8081 到 8099。

## 安全要求

- 仓库必须保持为 Private。
- 只邀请确实需要使用工具的同事。
- 不要提交 `schedule_data.db`、备份文件或任何真实 API 凭据。
- 不要删除或修改 `.gitignore` 中的数据库和密钥排除规则。
- 不要通过群聊、邮件截图或 GitHub Issue 发送 SecretId/SecretKey。
- 曾经暴露过的 SecretId/SecretKey 必须在腾讯会议后台轮换。
- 同事离职或不再需要使用时，应及时移除仓库权限；必要时同时轮换 API 凭据。
