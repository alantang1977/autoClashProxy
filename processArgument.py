import argparse

def processArgs(bRequiredExclusive=True):
    parser = argparse.ArgumentParser()
    parser.add_argument("--urlfile", type=str, default="source.url", help="指定下载clash订阅链接的文件")
    parser.add_argument("--push", action='store_true', help="将生成的clash配置文件上传至github")
    parser.add_argument("--retry", type=int, default=5, help="失败后重试的次数。默认数值为5次")
    parser.add_argument("--noDownload", action='store_true', help="不下载公开节点，使用本地配置文件")
    parser.add_argument("--noCheck", action='store_true', help="不检查当前配置文件中节点数量是否满足要求")

    parser.add_argument("--uiUrl", type=str, default="http://127.0.0.1", help="登录clah ui的地址")
    parser.add_argument("--uiPort", type=int, help="登录clah ui的端口")
    parser.add_argument("--secret", type=str, help="登录clah ui所需的密钥")
    parser.add_argument("--mixedPort", type=int, default=7890, help="clash的http代理端口")
    parser.add_argument("--timeout", type=int, default=3000, help="clash对节点进行延迟测试的超时时间")
    parser.add_argument("--delayUrl", type=str, default="https://www.youtube.com/generate_204", help="clash进行延迟测试的url")

    parser.add_argument("--defaultFile", type=str, default="default.config", help="生成配置文件所需要的模板文件")
    parser.add_argument("--configFile", type=str, default="list.yaml", help="最终生成的clash配置文件名称")
    parser.add_argument("--minProxyInConfig", type=int, default=10, help="生成配置文件所需要的最小节点数量")
    parser.add_argument("--maxProxyInConfig", type=int, default=2000, help="生成配置文件所允许的最大节点数量")
    parser.add_argument("--maxProxyAfterDelay", type=int, default=36, help="经过延迟测试后，允许输出的最大节点数量")
    parser.add_argument("--interval", type=int, default=360, help="clash代理组节点检测时间间隔")
    parser.add_argument("--flushFakeip", action='store_true', help="删除fakeip缓存")
    parser.add_argument("--log", type=str, default="", choices=["debug", "info", "warning", "error", "silent"])

    createClash = parser.add_mutually_exclusive_group(required=bRequiredExclusive)
    createClash.add_argument("--local", action='store_true', help="处理本地配置文件，生成clash配置文件。")
    createClash.add_argument("--download", action='store_true', help="下载公开的订阅文件，生成clash配置文件。")
    createClash.add_argument("--update", action='store_true', help="对所有节点进行延迟测试后，生成配置文件。")

    args = parser.parse_args()

    return args