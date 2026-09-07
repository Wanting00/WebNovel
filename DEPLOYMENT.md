# 服务器部署记录（AWS EC2 + Docker）

记录一次完整部署 WebNovel 到 AWS EC2 的实际操作步骤和命令，供复习/下次部署参考。

## 前提条件

- 代码已推送到 GitHub（`git remote add origin ...` + `git push`），`.env` 中 `GOOGLE_API_KEY` 留空（服务器上手动填）。
- `models/` 目录因体积过大（450MB+）没有随 git 提交，需要单独传输。
- 已在 AWS 控制台创建好 EC2 实例（Ubuntu），下载了密钥对 `.pem` 文件，放在本机 `C:\Users\<用户名>\.ssh\` 目录。
- 安全组已放行 22 端口（SSH），22335 端口（Streamlit 前端，最后一步再开）。

## 第 1 步：本机准备密钥文件权限

在本机 PowerShell 执行（`.pem` 权限过于开放会导致 SSH 拒绝连接）：

```powershell
icacls "$env:USERPROFILE\.ssh\WebNovel.pem" /inheritance:r
icacls "$env:USERPROFILE\.ssh\WebNovel.pem" /grant:r "$($env:USERNAME):(R)"
```

## 第 2 步：SSH 连接服务器

```powershell
ssh -o StrictHostKeyChecking=accept-new -i "$env:USERPROFILE\.ssh\WebNovel.pem" ubuntu@<公网IP>
```

首次连接会提示是否信任主机指纹，`accept-new` 参数自动接受，避免手动确认卡住。

## 第 3 步：（服务器上）安装 Docker

```bash
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker $USER
```

执行完 `usermod` 后，**必须退出重新连接**才能让用户组生效：

```bash
exit
```
然后重复第 2 步重新 SSH 连接。

验证安装：
```bash
docker version
docker compose version
```

## 第 4 步：（服务器上）克隆代码仓库

```bash
git clone https://github.com/Wanting00/WebNovel.git
cd WebNovel
```

> 如果仓库是私有的，HTTPS 方式会要求输入用户名+密码（密码需用 GitHub Personal Access Token，不是登录密码）。最简单的办法是先把仓库设为 Public 再 clone。

## 第 5 步：把本地模型文件传到服务器

因为 `models/` 目录没有进 git，需要单独用 `scp` 从本机传输。

服务器上先建好目标目录：
```bash
mkdir -p ~/WebNovel/models
```

**本机** PowerShell 执行（另开一个终端，不影响 SSH 会话）：
```powershell
scp -i "$env:USERPROFILE\.ssh\WebNovel.pem" -r "d:\WebNovel\models\paraphrase-multilingual-MiniLM-L12-v2" ubuntu@<公网IP>:~/WebNovel/models/
```

验证（服务器上）：
```bash
ls -lh ~/WebNovel/models/paraphrase-multilingual-MiniLM-L12-v2/
```

## 第 6 步：（服务器上）配置 `.env`

仓库自带的 `.env` 里 `GOOGLE_API_KEY` 是空的，需要手动填入：
```bash
nano .env
# 把 GOOGLE_API_KEY= 后面粘贴真实 Key，Ctrl+O 保存，Ctrl+X 退出
```
或者用 `sed` 一行替换（适合已知 Key 内容时脚本化操作）：
```bash
sed -i 's|^GOOGLE_API_KEY=.*|GOOGLE_API_KEY=你的key|' .env
```
确认 `USE_PROXY=false`（服务器在国外，不需要走本地代理）。

## 第 7 步：构建镜像

```bash
docker compose build
```

### 踩坑记录：磁盘空间不足

`requirements.txt` 里的 `torch` 默认会拉取 CUDA 相关依赖（几个GB的 nvidia-* 包），EC2 默认 28GB 系统盘很容易被写满，报错：
```
failed to extract layer ...: no space left on device
```

**排查命令：**
```bash
df -h /
docker system df
```

**清理已占用空间（构建失败留下的缓存）：**
```bash
docker builder prune -af
docker system prune -af
```

**根本修复**：在 [Dockerfile](Dockerfile) 里先单独安装 CPU 版 torch，避免 pip 拉取 CUDA 依赖（服务器没有 GPU，用不上）：
```dockerfile
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu
RUN pip install --no-cache-dir -r requirements.txt
```
改完在本机提交推送，服务器上 `git pull` 后重新 `docker compose build`。

## 第 8 步：启动容器

```bash
docker compose up -d
docker compose ps        # 确认两个容器都是 Up
```

## 第 9 步：验证后端

```bash
curl http://localhost:8000/health
# 期望输出：{"status":"ok","gemini_configured":true}
```

## 第 10 步：AWS 控制台放行前端端口

1. EC2 控制台 → 实例 → 安全 标签 → 点安全组
2. 编辑入站规则 → 添加规则
3. 类型：自定义 TCP，端口：**22335**，来源：`0.0.0.0/0`（或指定自己的 IP）
4. 保存

浏览器访问 `http://<公网IP>:22335` 验证。

## 常用运维命令

```bash
docker compose logs -f                          # 查看实时日志
docker compose down                             # 停止
docker compose up -d                            # 启动
git pull && docker compose build && docker compose up -d   # 更新代码后重新部署
docker system df                                # 查看磁盘占用
docker builder prune -af && docker system prune -af        # 清理无用镜像/缓存
```
