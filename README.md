# 光谱波长校准台

校准员提交标称波长与实测波长。独立领取进程按允差写出合格或超差。页面轮询直到结论出现。

## 端口

| 服务 | 地址 |
|------|------|
| 页面 | http://localhost:3195 |
| 接口 | http://localhost:8195 |
| PostgreSQL | localhost:54395 |

## 账号

| 用户 | 密码 | 权限 |
|------|------|------|
| calibrator | calib123456 | 可提交校准 |
| inspector | insp123456 | 只看 |

## 启动

```bash
cd projects/16-spectrum-wavelength-desk
docker compose up --build
```

## 验收

1. calibrator 登录后，种子「氦灯-587」合格、「汞灯-546」超差。
2. 再提交超差样条，先待处理再出超差。
3. inspector 不能提交。
