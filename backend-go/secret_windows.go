//go:build windows

package fastread

import (
	"encoding/base64"
	"syscall"
	"unsafe"
)

func unprotectDPAPI(encoded string) (string, error) {
	raw, e := base64.StdEncoding.DecodeString(encoded)
	if e != nil {
		return "", e
	}
	if len(raw) == 0 {
		return "", Error(500, "本地凭据无效")
	}
	type blob struct {
		Size uint32
		Data *byte
	}
	src := blob{uint32(len(raw)), &raw[0]}
	var out blob
	crypt := syscall.NewLazyDLL("crypt32.dll").NewProc("CryptUnprotectData")
	ok, _, err := crypt.Call(uintptr(unsafe.Pointer(&src)), 0, 0, 0, 0, 0, uintptr(unsafe.Pointer(&out)))
	if ok == 0 {
		return "", err
	}
	defer syscall.NewLazyDLL("kernel32.dll").NewProc("LocalFree").Call(uintptr(unsafe.Pointer(out.Data)))
	return string(unsafe.Slice(out.Data, int(out.Size))), nil
}
