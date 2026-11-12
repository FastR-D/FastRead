package fastread

import (
	"context"
	"encoding/json"
	"encoding/xml"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"regexp"
	"sort"
	"strings"
	"time"
)

type searchSourceResult struct {
	name   string
	papers []Row
	status Row
}

func SearchPublic(ctx context.Context, s *Store, query string, limit int) Row {
	ctx, cancel := context.WithTimeout(ctx, 22*time.Second)
	defer cancel()
	results := make(chan searchSourceResult, 3)
	for _, name := range []string{"arxiv", "crossref", "openalex"} {
		go func(name string) {
			key := "go-search:" + name + ":" + fmt.Sprint(limit) + ":" + query
			if cached, e := s.One("SELECT content FROM provider_cache WHERE key=? AND expires>?", key, Now()); e == nil {
				v := Object(cached["content"])
				results <- searchSourceResult{name, snapshotRows(v["papers"]), v["status"].(map[string]any)}
				return
			}
			if _, e := s.One("SELECT provider FROM provider_cooldown WHERE provider=? AND until>?", name, Now()); e == nil {
				results <- searchSourceResult{name, []Row{}, Row{"available": false, "reason": "rate_limited"}}
				return
			}
			papers, e := searchRegistry(ctx, name, query, limit)
			status := Row{"available": e == nil, "result_count": len(papers)}
			if e != nil {
				status["reason"] = "upstream_error"
				if strings.Contains(e.Error(), "429") {
					status["reason"] = "rate_limited"
					s.DB.Exec("INSERT OR REPLACE INTO provider_cooldown VALUES(?,?)", name, Now()+120)
				}
			} else {
				s.DB.Exec("INSERT OR REPLACE INTO provider_cache VALUES(?,?,?)", key, Encode(Row{"papers": papers, "status": status}), Now()+600)
			}
			results <- searchSourceResult{name, papers, status}
		}(name)
	}
	statuses := Row{}
	papers := []Row{}
	for i := 0; i < 3; i++ {
		select {
		case result := <-results:
			statuses[result.name] = result.status
			for _, paper := range result.papers {
				paper["discovery_sources"] = []string{result.name}
				papers = append(papers, paper)
			}
		case <-ctx.Done():
			i = 3
		}
	}
	for _, name := range []string{"arxiv", "crossref", "openalex"} {
		if statuses[name] == nil {
			statuses[name] = Row{"available": false, "reason": "deadline_exceeded"}
		}
	}
	dedup := map[string]int{}
	merged := []Row{}
	for _, paper := range papers {
		key := strings.ToLower(Str(paper["doi"]))
		if key == "" {
			key = Str(paper["id"])
		}
		if key == "" {
			key = lowerSpace(Str(paper["title"]))
		}
		if index, ok := dedup[key]; ok {
			old := merged[index]
			old["discovery_sources"] = append(old["discovery_sources"].([]string), paper["discovery_sources"].([]string)...)
			if Str(old["pdf_url"]) == "" {
				old["pdf_url"] = paper["pdf_url"]
			}
			continue
		}
		dedup[key] = len(merged)
		merged = append(merged, paper)
	}
	terms := textTerms(query)
	score := func(p Row) int {
		title := strings.ToLower(Str(p["title"]))
		n := 0
		for _, term := range terms {
			if strings.Contains(title, term) {
				n++
			}
		}
		return n
	}
	sort.SliceStable(merged, func(i, j int) bool { return score(merged[i]) > score(merged[j]) })
	if len(merged) > limit {
		merged = merged[:limit]
	}
	return Row{"papers": merged, "sources": statuses}
}
func registryGet(ctx context.Context, address string) ([]byte, error) {
	address, headers, e := routeArxiv(address)
	if e != nil {
		return nil, e
	}
	request, e := http.NewRequestWithContext(ctx, "GET", address, nil)
	if e != nil {
		return nil, e
	}
	request.Header.Set("User-Agent", "FastRead/4.0 (academic literature discovery)")
	for k, v := range headers {
		request.Header.Set(k, v)
	}
	response, e := (&http.Client{Timeout: 20 * time.Second, CheckRedirect: paperRedirect}).Do(request)
	if e != nil {
		return nil, e
	}
	defer response.Body.Close()
	if response.StatusCode != 200 {
		return nil, fmt.Errorf("registry HTTP %d", response.StatusCode)
	}
	return io.ReadAll(io.LimitReader(response.Body, 8<<20))
}
func searchRegistry(ctx context.Context, name, query string, limit int) ([]Row, error) {
	rows := []Row{}
	switch name {
	case "arxiv":
		clean := regexp.MustCompile(`[^\p{L}\p{N}\s.-]`).ReplaceAllString(query, " ")
		terms := strings.Fields(clean)
		if len(terms) > 12 {
			terms = terms[:12]
		}
		parts := []string{}
		for _, term := range terms {
			parts = append(parts, "all:"+term)
		}
		values := url.Values{"search_query": {`ti:"` + clean + `" OR (` + strings.Join(parts, " AND ") + ")"}, "max_results": {fmt.Sprint(limit)}, "sortBy": {"relevance"}}
		data, e := registryGet(ctx, "https://export.arxiv.org/api/query?"+values.Encode())
		if e != nil {
			return rows, e
		}
		var feed struct {
			Entries []struct {
				ID, Title, Summary, Published string
				Authors                       []struct{ Name string } `xml:"author"`
				Links                         []struct {
					Href  string `xml:"href,attr"`
					Title string `xml:"title,attr"`
					Type  string `xml:"type,attr"`
				} `xml:"link"`
				DOI string `xml:"doi"`
			} `xml:"entry"`
		}
		if e = xml.Unmarshal(data, &feed); e != nil {
			return rows, e
		}
		for _, entry := range feed.Entries {
			authors := []string{}
			for _, a := range entry.Authors {
				authors = append(authors, a.Name)
			}
			pdf := ""
			for _, link := range entry.Links {
				if link.Title == "pdf" || link.Type == "application/pdf" {
					pdf = link.Href
				}
			}
			rows = append(rows, Row{"id": entry.ID, "title": strings.Join(strings.Fields(entry.Title), " "), "abstract": strings.Join(strings.Fields(entry.Summary), " "), "authors": authors, "year": yearFromDate(entry.Published), "url": entry.ID, "pdf_url": pdf, "doi": entry.DOI, "venue": "arXiv"})
		}
	case "crossref":
		data, e := registryGet(ctx, "https://api.crossref.org/works?"+url.Values{"query.bibliographic": {query}, "rows": {fmt.Sprint(limit)}}.Encode())
		if e != nil {
			return rows, e
		}
		var payload struct {
			Message struct {
				Items []struct {
					DOI       string `json:"DOI"`
					Title     []string
					URL       string
					Container []string                         `json:"container-title"`
					Authors   []struct{ Given, Family string } `json:"author"`
					Published struct {
						Parts [][]int `json:"date-parts"`
					} `json:"published"`
					Link []struct{ URL, ContentType string }
				}
			}
		}
		if e = json.Unmarshal(data, &payload); e != nil {
			return rows, e
		}
		for _, item := range payload.Message.Items {
			if len(item.Title) == 0 {
				continue
			}
			authors := []string{}
			for _, author := range item.Authors {
				authors = append(authors, strings.TrimSpace(author.Given+" "+author.Family))
			}
			var year any
			if len(item.Published.Parts) > 0 && len(item.Published.Parts[0]) > 0 {
				year = item.Published.Parts[0][0]
			}
			venue := ""
			if len(item.Container) > 0 {
				venue = item.Container[0]
			}
			rows = append(rows, Row{"id": "doi:" + item.DOI, "doi": item.DOI, "title": item.Title[0], "authors": authors, "year": year, "url": item.URL, "venue": venue, "abstract": ""})
		}
	case "openalex":
		data, e := registryGet(ctx, "https://api.openalex.org/works?"+url.Values{"search": {query}, "per-page": {fmt.Sprint(limit)}}.Encode())
		if e != nil {
			return rows, e
		}
		var payload struct {
			Results []struct {
				ID, DOI, Title string
				Year           int `json:"publication_year"`
				Authorships    []struct {
					Author struct {
						DisplayName string `json:"display_name"`
					}
				}
				Location struct {
					Landing string `json:"landing_page_url"`
					PDF     string `json:"pdf_url"`
					Source  *struct {
						DisplayName string `json:"display_name"`
					}
				} `json:"primary_location"`
				OpenAccess struct {
					URL string `json:"oa_url"`
				} `json:"open_access"`
			}
		}
		if e = json.Unmarshal(data, &payload); e != nil {
			return rows, e
		}
		for _, item := range payload.Results {
			authors := []string{}
			for _, author := range item.Authorships {
				authors = append(authors, author.Author.DisplayName)
			}
			venue := ""
			if item.Location.Source != nil {
				venue = item.Location.Source.DisplayName
			}
			pdf := item.Location.PDF
			if pdf == "" {
				pdf = item.OpenAccess.URL
			}
			rows = append(rows, Row{"id": item.ID, "doi": strings.TrimPrefix(item.DOI, "https://doi.org/"), "title": item.Title, "authors": authors, "year": item.Year, "url": item.Location.Landing, "pdf_url": pdf, "venue": venue, "abstract": ""})
		}
	}
	return rows, nil
}
func discoverNeighbors(ctx context.Context, s *Store, paper, document Row) Row {
	anchors := []Row{}
	queries := []string{}
	if report, e := s.One("SELECT content FROM report_versions WHERE paper_id=? AND version_id=? ORDER BY created DESC LIMIT 1", paper["id"], document["document_version_id"]); e == nil {
		value := Object(report["content"])
		for _, section := range []string{"key_questions", "process", "contributions"} {
			for _, raw := range snapshotRows(value[section]) {
				text := Str(raw["question"])
				if text == "" {
					text = Str(raw["title"])
				}
				if text == "" {
					text = Str(raw["step"])
				}
				if text != "" {
					anchors = append(anchors, Row{"id": fmt.Sprintf("A%d", len(anchors)+1), "text": text, "type": section, "label": text})
					if len(queries) < 2 {
						queries = append(queries, trimRunes(text, 300))
					}
				}
			}
		}
	}
	queries = append(queries, trimRunes(Str(paper["title"]), 300))
	if len(anchors) == 0 {
		anchors = append(anchors, Row{"id": "A1", "text": paper["title"], "label": paper["title"], "type": "title"})
	}
	papers := []Row{}
	sources := Row{}
	seen := map[string]bool{}
	for _, query := range queries {
		result := SearchPublic(ctx, s, query, 20)
		for name, status := range result["sources"].(map[string]any) {
			sources[name] = status
		}
		for _, candidate := range snapshotRows(result["papers"]) {
			if lowerSpace(Str(candidate["title"])) == lowerSpace(Str(paper["title"])) {
				continue
			}
			key := Str(candidate["doi"])
			if key == "" {
				key = Str(candidate["id"])
			}
			if seen[key] {
				continue
			}
			seen[key] = true
			matched := []string{}
			overlap := []string{}
			title := strings.ToLower(Str(candidate["title"]) + " " + Str(candidate["abstract"]))
			for _, anchor := range anchors {
				count := 0
				for _, term := range textTerms(Str(anchor["text"])) {
					if strings.Contains(title, term) {
						count++
						overlap = append(overlap, term)
					}
				}
				if count > 0 {
					matched = append(matched, Str(anchor["id"]))
				}
			}
			candidate["matched_anchor_ids"] = matched
			candidate["matched_terms"] = overlap
			candidate["relevance_score"] = len(overlap)
			candidate["tags"] = []string{}
			candidate["shared_tags"] = []string{}
			papers = append(papers, candidate)
		}
	}
	sort.SliceStable(papers, func(i, j int) bool { return Num(papers[i]["relevance_score"]) > Num(papers[j]["relevance_score"]) })
	return Row{"papers": papers, "anchors": anchors, "queries": queries, "sources": sources, "document_version_id": document["document_version_id"], "evidence_status": "discovery_candidates_not_verified_support"}
}
