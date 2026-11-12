package fastread

import (
	"context"
	"crypto/sha256"
	"database/sql"
	"encoding/hex"
	"errors"
	"fmt"
	"html"
	"io"
	"net/http"
	"net/url"
	"os"
	"os/exec"
	"path/filepath"
	"regexp"
	"strconv"
	"strings"
	"time"
)

func parsePDF(ctx context.Context, path string) (Row, []Row, error) {
	parser := os.Getenv("FASTREAD_PDFTOTEXT")
	if parser == "" {
		parser = "pdftotext"
	}
	raw, e := exec.CommandContext(ctx, parser, "-enc", "UTF-8", "-layout", path, "-").Output()
	if e != nil {
		return nil, nil, errors.New("PDF text extraction failed")
	}
	segments := strings.Split(string(raw), "\f")
	if len(segments) > 0 && strings.TrimSpace(segments[len(segments)-1]) == "" {
		segments = segments[:len(segments)-1]
	}
	pages := []Row{}
	total := 0
	for i, text := range segments {
		text = strings.TrimSpace(text)
		total += len([]rune(text))
		pages = append(pages, Row{"page": i + 1, "text": text})
	}
	if total < 40 || len(pages) == 0 {
		return nil, nil, errors.New("PDF contains insufficient searchable text")
	}
	meta := Row{"title": strings.TrimSuffix(filepath.Base(path), filepath.Ext(path)), "authors": []string{}, "page_count": len(pages), "source": "pdf", "metadata_resolution": Row{"status": "pdf_extracted"}, "metadata_contract": Row{"parser_version": "poppler", "strategy_version": "native-go-v1"}}
	infoProgram := os.Getenv("FASTREAD_PDFINFO")
	if infoProgram == "" {
		infoProgram = "pdfinfo"
	}
	if info, e := exec.CommandContext(ctx, infoProgram, "-enc", "UTF-8", path).Output(); e == nil {
		for _, line := range strings.Split(string(info), "\n") {
			parts := strings.SplitN(line, ":", 2)
			if len(parts) != 2 {
				continue
			}
			key, value := strings.TrimSpace(parts[0]), strings.TrimSpace(parts[1])
			switch key {
			case "Title":
				if value != "" {
					meta["title"] = value
				}
			case "Author":
				if value != "" {
					meta["authors"] = []string{value}
				}
			}
		}
	}
	first := Str(pages[0]["text"])
	if title := Str(meta["title"]); title == "" || strings.HasSuffix(title, ".pdf") || regexp.MustCompile(`^[0-9a-f-]{32,36}$`).MatchString(title) {
		for _, line := range strings.Split(first, "\n") {
			candidate := strings.Join(strings.Fields(line), " ")
			if len([]rune(candidate)) >= 12 && len([]rune(candidate)) <= 300 {
				meta["title"] = candidate
				break
			}
		}
	}
	doiPattern := regexp.MustCompile(`(?i)\b10\.\d{4,9}/[^\s<>"\]]+`)
	if doi := doiPattern.FindString(first); doi != "" {
		meta["doi"] = strings.TrimRight(doi, ".,;)")
	}
	return meta, pages, nil
}

func downloadPaper(ctx context.Context, address string) ([]byte, string, error) {
	current, addressURL := address, (*url.URL)(nil)
	var e error
	addressURL, e = url.Parse(address)
	if e != nil {
		return nil, "", e
	}
	host := strings.ToLower(addressURL.Hostname())
	if host == "arxiv.org" || host == "www.arxiv.org" || host == "export.arxiv.org" {
		addressURL.Host = "arxiv.org"
		addressURL.Scheme = "https"
		addressURL.Path = strings.Replace(addressURL.Path, "/abs/", "/pdf/", 1)
		current = addressURL.String()
	}
	client := &http.Client{Timeout: 90 * time.Second, CheckRedirect: paperRedirect}
	for attempt := 0; attempt < 3; attempt++ {
		u, e := url.Parse(current)
		if e != nil || (u.Scheme != "http" && u.Scheme != "https") || u.Hostname() == "" || u.User != nil {
			return nil, "", errors.New("invalid paper URL")
		}
		if e = ValidatePublicURL(current); e != nil {
			return nil, "", e
		}
		requestURL, headers, e := routeArxiv(current)
		if e != nil {
			return nil, "", e
		}
		req, e := http.NewRequestWithContext(ctx, "GET", requestURL, nil)
		if e != nil {
			return nil, "", e
		}
		req.Header.Set("User-Agent", "FastRead/4.0 (research paper reader)")
		for k, v := range headers {
			req.Header.Set(k, v)
		}
		response, e := client.Do(req)
		if e != nil {
			return nil, "", e
		}
		if response.StatusCode < 200 || response.StatusCode > 299 {
			response.Body.Close()
			return nil, "", fmt.Errorf("paper download HTTP %d", response.StatusCode)
		}
		data, e := io.ReadAll(io.LimitReader(response.Body, 64<<20+1))
		response.Body.Close()
		if e != nil {
			return nil, "", e
		}
		if len(data) > 64<<20 {
			return nil, "", errors.New("PDF exceeds 64 MB")
		}
		if len(data) >= 5 && string(data[:5]) == "%PDF-" {
			return data, current, nil
		}
		if len(data) > 4<<20 {
			return nil, "", errors.New("paper page too large")
		}
		next := findPDFLink(string(data))
		if next == "" {
			return nil, "", errors.New("paper page has no PDF link")
		}
		ref, e := url.Parse(html.UnescapeString(next))
		if e != nil {
			return nil, "", e
		}
		current = response.Request.URL.ResolveReference(ref).String()
	}
	return nil, "", errors.New("PDF redirect limit reached")
}
func findPDFLink(page string) string {
	tags := regexp.MustCompile(`(?is)<meta\s+[^>]+>`).FindAllString(page, -1)
	attribute := regexp.MustCompile(`(?i)([\w:-]+)\s*=\s*["']([^"']*)["']`)
	for _, tag := range tags {
		attrs := map[string]string{}
		for _, m := range attribute.FindAllStringSubmatch(tag, -1) {
			attrs[strings.ToLower(m[1])] = m[2]
		}
		name := strings.ToLower(attrs["name"])
		if name == "" {
			name = strings.ToLower(attrs["property"])
		}
		if name == "citation_pdf_url" || name == "eprints.document_url" {
			return attrs["content"]
		}
	}
	for _, m := range regexp.MustCompile(`(?i)href\s*=\s*["']([^"']+\.pdf(?:\?[^"']*)?)["']`).FindAllStringSubmatch(page, -1) {
		return m[1]
	}
	return ""
}
func routeArxiv(address string) (string, map[string]string, error) {
	headers := map[string]string{}
	base := strings.TrimRight(os.Getenv("ARXIV_GATEWAY_URL"), "/")
	u, e := url.Parse(address)
	if e == nil && base != "" && (u.Hostname() == "arxiv.org" || u.Hostname() == "export.arxiv.org") {
		gateway, err := url.Parse(base)
		if err != nil || gateway.Scheme != "https" || gateway.Hostname() == "" || gateway.User != nil || gateway.RawQuery != "" || gateway.Fragment != "" {
			return "", nil, errors.New("invalid arxiv gateway configuration")
		}
		if u.Path != "/api/query" && !regexp.MustCompile(`^/(?:pdf|abs)/(?:\d{4}\.\d{4,5}(?:v\d+)?|[a-z-]+/\d{7}(?:v\d+)?)(?:\.pdf)?$`).MatchString(u.Path) {
			return "", nil, errors.New("unsupported arxiv gateway path")
		}
		token := os.Getenv("ARXIV_GATEWAY_API_KEY")
		if token == "" {
			return "", nil, errors.New("missing arxiv gateway key")
		}
		headers["X-FastRead-Gateway-Key"] = token
		return base + u.RequestURI(), headers, nil
	}
	return address, headers, nil
}

func paperRedirect(request *http.Request, via []*http.Request) error {
	if len(via) >= 10 {
		return errors.New("too many redirects")
	}
	gateway, _ := url.Parse(os.Getenv("ARXIV_GATEWAY_URL"))
	if gateway != nil && gateway.Host != "" && request.URL.Host == gateway.Host && len(via) > 0 && via[0].URL.Host == gateway.Host {
		return nil
	}
	request.Header.Del("X-FastRead-Gateway-Key")
	return ValidatePublicURL(request.URL.String())
}

func executeImport(ctx context.Context, s *Store, job Row, owner string, payload Row) error {
	relative := Str(payload["path"])
	address := Str(payload["url"])
	if Str(job["kind"]) == "import_url" {
		data, finalURL, e := downloadPaper(ctx, address)
		if e != nil {
			return e
		}
		address = finalURL
		relative = "files/" + Str(job["id"]) + ".pdf"
		target := filepath.Join(s.Root, filepath.FromSlash(relative))
		if e = os.WriteFile(target+".tmp", data, 0600); e != nil {
			return e
		}
		if e = os.Rename(target+".tmp", target); e != nil {
			return e
		}
	}
	path, e := fileInside(s.Root, relative)
	if e != nil {
		return e
	}
	metadata, pages, e := parsePDF(ctx, path)
	if e != nil {
		return e
	}
	if address != "" {
		metadata["url"] = address
		metadata["source_url"] = Str(payload["url"])
	}
	for _, key := range []string{"title", "authors", "venue", "doi", "year"} {
		if value, ok := payload[key]; ok && value != nil && Str(value) != "" {
			metadata[key] = value
		}
	}
	if source := Str(payload["source"]); source != "" {
		metadata["import_origin"] = Row{"source": source, "external_id": payload["external_id"]}
	}
	if name := Str(payload["filename"]); name != "" {
		metadata["filename"] = name
	}
	principal := Principal{UserID: Str(job["user_id"]), WorkspaceID: Str(job["workspace_id"])}
	app := &App{Store: s}
	config, modelErr := app.ChooseModel(principal, Str(payload["provider_id"]), Str(payload["model"]))
	bid := Str(payload["knowledge_id"])
	var result Row
	e = s.Transaction(func(tx *sql.Tx) error {
		if e := assertLease(tx, job, owner); e != nil {
			return e
		}
		var e error
		result, e = ingestDocument(tx, principal.WorkspaceID, metadata, pages, relative, Str(payload["paper_id"]))
		if e != nil {
			return e
		}
		if _, e = EnqueueTx(tx, principal, "index", Row{}, "index:"+Str(result["version_id"]), Str(result["paper_id"]), Str(result["version_id"]), false); e != nil {
			return e
		}
		if bid != "" {
			if _, e = One(tx, "SELECT id FROM knowledge_bases WHERE id=? AND workspace_id=?", bid, principal.WorkspaceID); e != nil {
				return e
			}
			if _, e = tx.Exec("INSERT OR IGNORE INTO knowledge_papers VALUES(?,?,'manual',?)", bid, result["paper_id"], Now()); e != nil {
				return e
			}
		}
		organize, ok := payload["organize"].(bool)
		if !ok {
			organize = true
		}
		if organize {
			if modelErr == nil {
				config["knowledge_id"] = bid
				child, e := EnqueueTx(tx, principal, "organize", config, "organize:"+Str(job["id"]), Str(result["paper_id"]), Str(result["version_id"]), true)
				if e == nil {
					result["organize_job_id"] = child["id"]
				} else {
					result["organize_notice"] = "论文已保存；请检查模型额度后启动智能整理。"
				}
			} else {
				result["organize_notice"] = "论文已保存；配置模型后可启动智能整理。"
			}
		}
		return completeJob(tx, job, result)
	})
	if e == nil && bid != "" {
		app.scheduleQuestions(principal, bid)
	}
	return e
}

func ingestDocument(tx *sql.Tx, workspace string, metadata Row, pages []Row, file, paperID string) (Row, error) {
	if len(pages) == 0 {
		return nil, errors.New("document has no pages")
	}
	content := sha256.Sum256([]byte(Encode(pages)))
	fingerprint := hex.EncodeToString(content[:])
	identity := "content:" + fingerprint
	identities := []string{identity}
	if doi := strings.ToLower(strings.TrimSpace(Str(metadata["doi"]))); doi != "" {
		doi = strings.TrimPrefix(doi, "https://doi.org/")
		identity = "doi:" + doi
		identities = append(identities, identity)
	}
	arxiv := regexp.MustCompile(`(?:arxiv\.org/(?:abs|pdf)/)(\d{4}\.\d{4,5}|[a-z-]+/\d{7})`)
	if match := arxiv.FindStringSubmatch(Str(metadata["url"])); len(match) > 1 {
		key := "arxiv:" + match[1]
		identities = append(identities, key)
		if strings.HasPrefix(identity, "content:") {
			identity = key
		}
		metadata["arxiv_id"] = match[1]
	}
	var existing Row
	var e error
	if paperID != "" {
		existing, e = One(tx, "SELECT * FROM papers WHERE id=? AND workspace_id=? AND archived=0", paperID, workspace)
		if e != nil {
			return nil, e
		}
	} else {
		for _, key := range identities {
			row, err := One(tx, "SELECT p.* FROM papers p JOIN paper_identities i ON i.paper_id=p.id WHERE i.workspace_id=? AND i.identity=?", workspace, key)
			if err == nil {
				if existing != nil && Str(existing["id"]) != Str(row["id"]) {
					return nil, errors.New("paper identity conflict")
				}
				existing = row
			} else if err != sql.ErrNoRows {
				return nil, err
			}
		}
		if existing == nil {
			existing, e = One(tx, "SELECT * FROM papers WHERE workspace_id=? AND identity=?", workspace, identity)
			if e != nil && e != sql.ErrNoRows {
				return nil, e
			}
		}
	}
	if existing != nil {
		paperID = Str(existing["id"])
		oldMeta := Object(existing["metadata"])
		if Str(oldMeta["source"]) == "fastnews" {
			for _, key := range []string{"title", "authors", "year", "venue", "abstract", "url", "external_id"} {
				if value := oldMeta[key]; value != nil && Str(value) != "" {
					metadata[key] = value
				}
			}
			metadata["source"] = "fastnews"
			metadata["awaiting_file"] = false
		}
		if version := Str(existing["active_version"]); version != "" {
			oldPages, e := Rows(tx, "SELECT number AS page,text FROM pages WHERE version_id=? ORDER BY number", version)
			if e != nil {
				return nil, e
			}
			if Encode(oldPages) == Encode(pages) {
				_, e = tx.Exec("UPDATE papers SET archived=0 WHERE id=?", paperID)
				return Row{"paper_id": paperID, "version_id": version, "deduplicated": true}, e
			}
		}
	} else {
		paperID = UID()
		_, e = tx.Exec("INSERT INTO papers(id,workspace_id,identity,title,metadata,created) VALUES(?,?,?,?,?,?)", paperID, workspace, identity, Str(metadata["title"]), Encode(metadata), Now())
		if e != nil {
			return nil, e
		}
	}
	for _, key := range identities {
		if _, e = tx.Exec("INSERT OR IGNORE INTO paper_identities VALUES(?,?,?)", workspace, key, paperID); e != nil {
			return nil, e
		}
	}
	old, e := One(tx, "SELECT id FROM document_versions WHERE paper_id=? AND fingerprint=?", paperID, fingerprint)
	version := UID()
	duplicate := e == nil
	if duplicate {
		version = Str(old["id"])
	} else if e != sql.ErrNoRows {
		return nil, e
	} else {
		_, e = tx.Exec("INSERT INTO document_versions VALUES(?,?,?,?,?,?)", version, paperID, fingerprint, Encode(metadata), file, Now())
		if e != nil {
			return nil, e
		}
		for _, page := range pages {
			if _, e = tx.Exec("INSERT INTO pages VALUES(?,?,?)", version, page["page"], page["text"]); e != nil {
				return nil, e
			}
			for ordinal, text := range chunkText(Str(page["text"]), 1600) {
				if _, e = tx.Exec("INSERT INTO evidence_chunks VALUES(?,?,?,?,?)", fmt.Sprintf("%s:p%v:c%d", version, page["page"], ordinal), version, page["page"], ordinal, text); e != nil {
					return nil, e
				}
			}
		}
	}
	_, e = tx.Exec("UPDATE papers SET title=?,metadata=?,active_version=?,archived=0 WHERE id=?", metadata["title"], Encode(metadata), version, paperID)
	return Row{"paper_id": paperID, "version_id": version, "deduplicated": duplicate}, e
}

func yearFromDate(v string) any {
	if len(v) >= 4 {
		n, e := strconv.Atoi(v[:4])
		if e == nil {
			return n
		}
	}
	return nil
}
