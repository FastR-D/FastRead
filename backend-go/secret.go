package fastread

import (
	"crypto/aes"
	"crypto/cipher"
	"crypto/rand"
	"encoding/base64"
	"errors"
	"os"
	"path/filepath"
	"strings"
)

const secretPrefix = "filekey:v1:"

var secretAAD = []byte("FastRead provider secret filekey v1")

func secretKey(root string, create bool) ([]byte, error) {
	keyRoot := os.Getenv("FASTREAD_DATA_ROOT")
	if keyRoot == "" {
		keyRoot = root
	}
	path := filepath.Join(keyRoot, "provider-secret.key")
	key, e := os.ReadFile(path)
	if os.IsNotExist(e) && create {
		if e = os.MkdirAll(keyRoot, 0700); e != nil {
			return nil, e
		}
		key = make([]byte, 32)
		if _, e = rand.Read(key); e != nil {
			return nil, e
		}
		f, e := os.OpenFile(path, os.O_WRONLY|os.O_CREATE|os.O_EXCL, 0600)
		if os.IsExist(e) {
			return secretKey(root, false)
		}
		if e != nil {
			return nil, e
		}
		_, e = f.Write(key)
		_ = f.Close()
		if e != nil {
			return nil, e
		}
	}
	if e != nil && !os.IsNotExist(e) {
		return nil, e
	}
	if len(key) != 32 {
		return nil, errors.New("invalid provider encryption key")
	}
	return key, nil
}
func (s *Store) ProtectSecret(value string) (string, error) {
	key, e := secretKey(s.Root, true)
	if e != nil {
		return "", e
	}
	block, e := aes.NewCipher(key)
	if e != nil {
		return "", e
	}
	g, e := cipher.NewGCM(block)
	if e != nil {
		return "", e
	}
	nonce := make([]byte, g.NonceSize())
	if _, e = rand.Read(nonce); e != nil {
		return "", e
	}
	data := g.Seal(nil, nonce, []byte(value), secretAAD)
	tag := data[len(data)-g.Overhead():]
	payload := append(append(nonce, tag...), data[:len(data)-g.Overhead()]...)
	return secretPrefix + base64.StdEncoding.EncodeToString(payload), nil
}
func (s *Store) UnprotectSecret(value string) (string, error) {
	if strings.HasPrefix(value, "dpapi:v1:") {
		return unprotectDPAPI(strings.TrimPrefix(value, "dpapi:v1:"))
	}
	if !strings.HasPrefix(value, secretPrefix) {
		return value, nil
	}
	key, e := secretKey(s.Root, false)
	if e != nil {
		return "", e
	}
	data, e := base64.StdEncoding.DecodeString(strings.TrimPrefix(value, secretPrefix))
	if e != nil || len(data) < 28 {
		return "", errors.New("invalid encrypted provider value")
	}
	block, e := aes.NewCipher(key)
	if e != nil {
		return "", e
	}
	g, e := cipher.NewGCM(block)
	if e != nil {
		return "", e
	}
	payload := append(append([]byte{}, data[28:]...), data[12:28]...)
	out, e := g.Open(nil, data[:12], payload, secretAAD)
	return string(out), e
}
