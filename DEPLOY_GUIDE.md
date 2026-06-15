# 部署指南：医美社媒运营助手 → Railway

## 一、前期准备：获取两个API Key

### 1. Anthropic API Key（Claude模型）
1. 打开 https://console.anthropic.com 并登录/注册
2. 左侧菜单 → **API Keys** → **Create Key**
3. 复制保存（只显示一次），命名建议：`medagent-key`
4. 进入 **Billing**，充值少量金额（建议先充 $5 测试）

### 2. Voyage AI API Key（知识库向量化，用于检索产品资料）
1. 打开 https://dash.voyageai.com 并登录/注册（可用Google账号）
2. 进入 **API Keys** 页面，创建一个Key并复制保存
3. Voyage AI 有免费额度（每月200M tokens），个人使用基本够用

---

## 二、把代码推到GitHub

> 这是Railway部署的前提：Railway从GitHub仓库读取代码。

1. 打开 https://github.com，注册/登录账号
2. 点击右上角 **+** → **New repository**
3. 仓库名填 `medagent`（或任意名字），选择 **Private**（私有，防止别人看到代码），点击 **Create repository**
4. 创建后页面会提示上传文件，点击 **uploading an existing file**
5. 把我给你的压缩包（`medagent.zip`）**解压后的所有文件**（不要打包成zip上传，要把里面的文件/文件夹直接拖进去）拖拽到上传区域
   - 确保包含：`main.py`、`ingest.py`、`requirements.txt`、`Procfile`、`static/index.html`
6. 滚动到底部，点击 **Commit changes**

---

## 三、在Railway上部署

1. 打开 https://railway.app，用GitHub账号登录（一键授权即可）
2. 点击 **New Project** → **Deploy from GitHub repo**
3. 选择刚才创建的 `medagent` 仓库 → 点击 **Deploy Now**
4. Railway会自动识别 `requirements.txt` 和 `Procfile`，开始构建（第一次构建需要2-5分钟）

---

## 四、配置环境变量（关键步骤）

1. 部署完成后，点击你的项目 → 点击服务卡片（通常叫 `medagent`）
2. 顶部Tab选择 **Variables**
3. 点击 **New Variable**，依次添加以下三个变量：

| 变量名 | 值 |
|---|---|
| `ANTHROPIC_API_KEY` | 第一步获取的 Anthropic Key |
| `VOYAGE_API_KEY` | 第一步获取的 Voyage Key |
| `CHROMA_PATH` | `/data/chroma_db` |

4. 添加完成后，Railway会自动重新部署（右上角会显示部署进度）

---

## 五、（重要）添加持久化存储 Volume

如果不做这一步，**每次重新部署，知识库里上传的资料会全部消失**（因为Chroma数据存在容器临时磁盘上）。

1. 在项目页面，点击 **+ New** → **Volume**
2. 挂载路径（Mount Path）填：`/data`
3. 大小默认即可（1GB足够存几十份产品文档的向量）
4. 保存后Railway会自动重启服务

> 这一步配合上面 `CHROMA_PATH=/data/chroma_db` 一起生效，知识库数据会持久保存。

---

## 六、获取访问链接 & 测试

1. 在项目页面 → 点击服务 → 顶部Tab选择 **Settings**
2. 找到 **Networking** 区域 → 点击 **Generate Domain**
3. Railway会生成一个形如 `medagent-production-xxxx.up.railway.app` 的网址
4. 打开这个网址，应该能看到我们做好的对话界面

### 测试步骤
1. 先在左侧"产品资料库"上传一份产品Word/PDF文档，等待显示"已导入，共XX段"
2. 在对话框输入：「2C方向，给我3个公众号选题」，回车发送
3. 等待几秒应该会有回复（首次调用可能稍慢）

---

## 七、常见问题排查

| 问题现象 | 可能原因 / 解决方法 |
|---|---|
| 页面打不开 / 502错误 | 等待1-2分钟构建完成；查看Railway项目的 **Deployments** 日志找报错信息 |
| 上传文件报错 | 检查文件是否为 `.pdf` 或 `.docx`；检查 `VOYAGE_API_KEY` 是否正确配置 |
| 对话报错"ANTHROPIC_API_KEY 未配置" | 检查Variables里的Key名称是否完全一致（大小写敏感），保存后等待重新部署 |
| 知识库内容重启后消失 | 确认已添加Volume并挂载到 `/data`，且 `CHROMA_PATH=/data/chroma_db` |
| 联网搜索没生效 | 确认对话框下方"联网搜索热点"勾选框已勾选 |
| Claude API报错额度不足 | 去 console.anthropic.com 的Billing页面检查余额 |

---

## 八、成本预估

- **Railway**：免费试用额度用完后约 $5/月（Hobby Plan）起
- **Anthropic API**：按使用量计费，日常文案生成单次对话约 $0.01-0.05，每月几十次使用预计 $5-20
- **Voyage AI**：免费额度通常够个人使用，超出后按量计费（很便宜）

---

## 后续维护

- **更新代码**：以后如果要修改功能，在GitHub仓库里编辑文件并Commit，Railway会自动重新部署
- **更换/添加产品资料**：直接在网页左侧上传新文档，或删除旧文档重新上传
