# OpenAlex API Reference

OpenAlex is a free, open catalog of 240M+ scholarly works. No authentication required.

**Base URL**: `https://api.openalex.org`

## Rate Limits

| Pool | Rate | How to enable |
|------|------|---------------|
| Default | 1 req/sec | - |
| Polite | 10 req/sec | Add `mailto=you@email.com` |
| Daily limit | 100k requests | - |

## Essential Endpoints

### Search Works

```
GET /works?search=cryopreservation+toxicity&per-page=25&mailto=you@email.com
```

### Get Single Work

```
GET /works/W2741809807
GET /works/https://doi.org/10.1234/example
```

### Find Citing Works

```
GET /works?filter=cites:W2741809807&per-page=50
```

### Batch Lookup (up to 50 IDs)

```
GET /works?filter=openalex_id:W123|W456|W789&per-page=50
```

## Key Filters

```
publication_year:2023           # Exact year
publication_year:>2020          # After 2020
cited_by_count:>100             # Highly cited
is_oa:true                      # Open access only
type:journal-article            # Article type
authorships.author.id:A123      # By author ID
authorships.institutions.id:I45 # By institution ID
```

Combine filters with comma (AND): `?filter=publication_year:2023,is_oa:true`

## Response Structure

```json
{
  "meta": {"count": 1234, "page": 1, "per_page": 25},
  "results": [
    {
      "id": "https://openalex.org/W2741809807",
      "doi": "https://doi.org/10.1234/example",
      "title": "Paper Title",
      "publication_date": "2023-01-15",
      "abstract_inverted_index": {...},
      "primary_location": {"pdf_url": "..."},
      "best_oa_location": {"pdf_url": "..."},
      "referenced_works": ["https://openalex.org/W123", ...],
      "related_works": ["https://openalex.org/W456", ...],
      "cited_by_count": 42
    }
  ]
}
```

## Reconstruct Abstract

```python
def reconstruct_abstract(inverted_index):
    if not inverted_index:
        return ""
    positions = [(pos, word) for word, indices in inverted_index.items() for pos in indices]
    positions.sort()
    return " ".join(w for _, w in positions)
```

## Get PDF URLs

Check in order:

1. `best_oa_location.pdf_url`
2. `primary_location.pdf_url`
3. Each `locations[].pdf_url`

## Two-Step Entity Lookup

> [!WARNING]
> Don't filter by names directly. Get the ID first.

```
# WRONG: ?filter=author_name:Einstein

# CORRECT:
1. GET /authors?search=einstein → get ID "A5023888391"
2. GET /works?filter=authorships.author.id:A5023888391
```

## Performance Tips

1. Use `per-page=200` (max) for bulk fetches
2. Use `select=id,title,doi` to limit fields
3. Batch IDs with pipe: `filter=doi:10.1/a|10.2/b|10.3/c`
4. Always add `mailto=` for 10x rate limit
5. Implement exponential backoff for errors

## Additional References

See <https://docs.openalex.org/api-guide-for-llms> for more information.
