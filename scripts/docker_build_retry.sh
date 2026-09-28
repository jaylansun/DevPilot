#!/usr/bin/env bash
# 只重试基础镜像元数据/认证令牌请求的网络瞬断；保留实时日志和原始退出码。
set -uo pipefail

if [ "$#" -eq 0 ]; then
    echo '用法：bash scripts/docker_build_retry.sh docker build ...' >&2
    exit 2
fi

log_file=$(mktemp "${TMPDIR:-/tmp}/devpilot-docker-build.XXXXXX") || exit 1
trap 'rm -f "$log_file"' EXIT
metadata_error='failed to (resolve source metadata|fetch (anonymous|oauth) token)'
network_error='TLS handshake timeout|i/o timeout|context deadline exceeded|connection reset by peer|unexpected EOF|: EOF([[:space:]]|$)'
network_error+='|Bad Gateway|Service Unavailable|Gateway Timeout|unexpected status.*: (500|502|503|504)([^0-9]|$)'

for attempt in 1 2 3; do
    echo "镜像构建：第 ${attempt}/3 次尝试"
    "$@" 2>&1 | tee "$log_file"
    statuses=("${PIPESTATUS[@]}")
    status=${statuses[0]}
    if [ "${statuses[1]}" -ne 0 ]; then
        exit "${statuses[1]}"
    fi
    if [ "$status" -eq 0 ]; then
        exit 0
    fi

    # 同一条最终错误必须同时包含元数据/令牌失败和可重试的网络原因。
    # 编译、测试、权限、标签不存在等失败不重试，取消信号也不能重启构建。
    if [ "$status" -ge 128 ] || ! grep -Eq \
        "${metadata_error}.*(${network_error})" \
        "$log_file"; then
        echo '构建失败不属于可重试的镜像仓库网络错误，立即停止。' >&2
        exit "$status"
    fi
    if [ "$attempt" -eq 3 ]; then
        echo '镜像仓库网络请求连续失败；请检查 Docker 引擎或 OrbStack 的代理连接。' >&2
        exit "$status"
    fi
    delay=$((attempt * 5))
    echo "镜像仓库连接暂时失败，${delay} 秒后重试，已完成的构建层仍可复用。" >&2
    sleep "$delay" || exit "$?"
done
