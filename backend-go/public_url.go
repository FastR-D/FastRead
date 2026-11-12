package fastread

import (
	"context"
	"net"
	"net/netip"
	"net/url"
	"strings"
	"time"
)

// ValidatePublicURL keeps user-supplied fetches outside the service's local network.
func ValidatePublicURL(address string) error {
	u, e := url.Parse(address)
	if e != nil || (u.Scheme != "http" && u.Scheme != "https") || u.Hostname() == "" || u.User != nil {
		return Error(422, "需要公开的 HTTP/HTTPS 地址")
	}
	host := strings.TrimSuffix(strings.ToLower(u.Hostname()), ".")
	if host == "metadata.google.internal" || strings.HasSuffix(host, ".metadata.google.internal") {
		return Error(422, "不允许访问内部服务地址")
	}
	addresses := []netip.Addr{}
	if ip, err := netip.ParseAddr(host); err == nil {
		addresses = append(addresses, ip)
	} else {
		ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
		defer cancel()
		addresses, e = net.DefaultResolver.LookupNetIP(ctx, "ip", host)
		if e != nil || len(addresses) == 0 {
			return Error(422, "无法解析服务地址")
		}
	}
	fakeIP := netip.MustParsePrefix("198.18.0.0/15")
	shared := netip.MustParsePrefix("100.64.0.0/10")
	for _, ip := range addresses {
		ip = ip.Unmap()
		if fakeIP.Contains(ip) {
			continue
		}
		if !ip.IsGlobalUnicast() || ip.IsPrivate() || ip.IsLoopback() || ip.IsLinkLocalUnicast() || shared.Contains(ip) || ip.String() == "169.254.169.254" {
			return Error(422, "不允许访问内部服务地址")
		}
	}
	return nil
}
