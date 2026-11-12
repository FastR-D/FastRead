//go:build !windows

package fastread

import "errors"

func unprotectDPAPI(string) (string, error) {
	return "", errors.New("Windows-protected provider credential requires Windows")
}
