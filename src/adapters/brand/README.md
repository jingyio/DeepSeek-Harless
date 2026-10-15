# GeneLoop 品牌资产

`geneloop.jpg` 为用户于 2026-10-14 提供的原始 Logo，原样保存，SHA-256：
`96dd2571f1881eed9c49f2a7e690f20b65f5ee07468e2788e8e9f1731aa97f3b`。

账号页面和客户端仅通过 CSS 视窗显示图标区域，不改写原图。客户端使用 Harness 的三个公开品牌 slot（`sidebar.brand.mark`、`sidebar.brand.name`、`conversation.hero.brand.mark`），以 priority -100 覆盖默认展示；不修改上游包。登录、注册、设置和网页标题使用 GeneLoop，模型名称、提供商和协议标识保留实际含义。

网关允许匿名读取固定 `/assets/geneloop.jpg`，让登录页加载 Logo；该路由不接受文件路径参数，不改变账号或产物的访问权限。账号页 CSP 只增加同源图片。直接 Harness 入口也注册同一路由。
