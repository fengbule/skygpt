# SkyGPT

ChatGPT 账号自动注册工具，支持 CPA (CLIProxyAPI) 认证文件生成。

## 功能特性

- WebUI 界面操作
- 手动输入邮箱和验证码
- 手动输入手机号和验证码
- 代理节点管理（手动输入、订阅导入、代理池）
- 代理可用性检测和测试
- 并发注册支持
- CPA 认证文件自动生成
- Docker 部署支持

## 快速开始

### 方式一：直接运行

```bash
pip install -r requirements.txt
python web/app.py
```

访问 http://localhost:5000

### 方式二：Docker 单镜像部署

```bash
docker build -t skygpt .
docker run -d -p 5000:5000 skygpt
```

### 方式三：Docker Compose 部署

```bash
docker-compose up -d
```

## 使用说明

1. 打开 WebUI，输入邮箱地址
2. 选择代理配置（可选）
3. 点击"开始注册"
4. 在任务页面查看进度
5. 如需输入验证码，在任务页面提交
6. 注册完成后，在 CPA 文件页面下载认证文件

## CPA 认证文件

生成的 CPA 文件格式：

```json
{
  "access_token": "...",
  "account_id": "...",
  "disabled": false,
  "email": "...",
  "expired": "...",
  "id_token": "...",
  "last_refresh": "...",
  "refresh_token": "...",
  "type": "codex"
}
```

将文件上传到 CLIProxyAPI 即可使用。

## License

MIT