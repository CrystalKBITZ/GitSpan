GitSpan
 
GitHub → Gitee 仓库一键迁移工具
 
✨功能
 
- ✅ Git完整镜像克隆GitHub仓库，缓存复用，减少重复下载
- ✅ 自动解析GitHub HTTPS/SSH链接，提取仓库名称
- ✅ 自动检测、创建Gitee公有/私有仓库
- ✅ 两种同步模式：增量同步 / 强制镜像覆盖同步
- ✅ 完整迁移所有Git分支、版本Tag标签
- ✅ 自动同步GitHub仓库简介、主页信息到Gitee
- ✅ 迁移GitHub Releases发行版，自动下载全部Release附件到本地
- ✅ GUI图形界面，右键菜单、密码显示隐藏开关
- ✅ 自定义缓存目录、附件保存目录，配置自动持久化保存
- ✅ 实时迁移日志输出，预计完成时间显示
- ✅ 网络失败自动重试，SSL异常容错，敏感令牌日志脱敏
 
⚠️当前限制
 
- Release附件仅本地下载，Gitee接口不支持上传附件，需要网页端手动上传
- 仅支持迁移公开GitHub仓库，暂不支持私有GitHub仓库
- 不迁移Issues、PR、Wiki、评论等非Git代码数据
- 单次只支持迁移单个仓库
 
使用
 
1. 填入Gitee私人令牌（需要仓库读写权限）
2. 填入GitHub公开仓库地址
3. 按需调整选项：私有仓库、迁移Release、强制镜像、自定义路径
4. 点击【开始迁移】等待完成
 
 
 
GitSpan
 
GitHub to Gitee one‑click repository migration tool
 
✨ Features
 
- ✅ Complete Git mirror clone for GitHub repositories, cache reuse to avoid repeated downloads
- ✅ Automatically parse GitHub HTTPS/SSH links and extract repository name
- ✅ Auto‑detect and create Gitee public / private repositories
- ✅ Two synchronization modes: Incremental Sync / Force Mirror Overwrite Sync
- ✅ Fully migrate all Git branches and version tags
- ✅ Automatically sync GitHub repository description and homepage info to Gitee
- ✅ Migrate GitHub Releases, auto‑download all release assets to local disk
- ✅ GUI desktop interface, right‑click menu, token show/hide toggle
- ✅ Customizable cache and asset storage path, auto‑persist configuration
- ✅ Real‑time migration log output, estimated completion time display
- ✅ Auto‑retry on network failure, SSL error tolerance, sensitive token desensitization in logs
 
⚠️ Limitations
 
- Release assets are only downloaded locally. Gitee API does not support asset uploading, manual upload via web page is required.
- Only public GitHub repositories are supported. Private GitHub repositories are not available for now.
- Non‑Git data such as Issues, PRs, Wiki and comments will not be migrated.
- Only one repository can be migrated at a time.
 
Usage
 
1. Fill in your Gitee personal access token (repository read‑write permission required)
2. Paste the URL of public GitHub repository
3. Adjust options as needed: private repository, migrate Releases, force mirror, custom storage paths
4. Click  Start Migration  and wait for task completion
