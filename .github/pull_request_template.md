## 变更目的

说明本次变更解决的业务问题，以及涉及的模块。

## 验证

- [ ] 已运行相关聚焦测试
- [ ] 已运行非集成快速回归
- [ ] 已运行 `python scripts/dev/project_context.py snapshot`
- [ ] 已运行 `python scripts/dev/project_context.py audit-docs`
- [ ] 已运行 `python scripts/dev/project_context.py check`
- [ ] ERPNext 写入（如有）仅发生在明确的测试账套
- [ ] 写操作具有确认、幂等 request_id 和写后回读

## 数据与安全

- [ ] 未提交 `.env`、`.secrets`、凭据、数据库备份或运行日志
- [ ] 未提交真实业务单据或未经授权的原始资料
- [ ] 新增数据包已记录来源、版本和 SHA-256

## 回滚与影响

说明数据迁移、兼容性、回滚方式和需要人工复核的内容。
