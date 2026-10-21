# Ingress platform mapping (deferred adapters)

Shared threads are surface-agnostic. IM platforms link via `ingress_thread_links` (anchor key: platform + channel + thread root ts).

| Platform | Anchor key | Passive mirror (v1) | Identity |
| -------- | ----------- | ------------------- | -------- |
| Slack | `platform=slack`, channel id, `slack_thread_root_ts` | Yes for shared + anchored channel threads | Slack external identity |
| WeCom | (planned) corp app / group chat + root msg id | TBD | `LoginMethod.wecom` |
| Lark/Feishu | (planned) chat id + thread id from payload | TBD | Feishu identity source |
| Discord | (planned) guild channel + thread id | TBD | New identity source |

v1 ships Slack only (`SlackIngressService`). A generic `IngressAdapter` protocol and cross-platform dedupe table are deferred until a second platform is scheduled.
