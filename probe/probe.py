import requests
H={"Content-Type":"application/json","Accept":"application/json","Accept-Language":"en-US","User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36"}
B="https://walmart.wd504.myworkdayjobs.com/wday/cxs/walmart/WalmartExternal/jobs"
r=requests.post(B,json={"appliedFacets":{},"limit":20,"offset":0,"searchText":"(IND) data scientist"},headers=H,timeout=30)
d=r.json() if r.ok else {}
print("::notice::WD",r.status_code,"total",d.get("total"),r.text[:200] if not r.ok else "")
for j in d.get("jobPostings",[])[:8]:
    print("::notice::JOB",j.get("title"),"|",j.get("locationsText"),"|",j.get("postedOn"),"|",j.get("externalPath"))
for f in d.get("facets",[]):
    fp=f.get("facetParameter")
    vals=f.get("values",[])
    nested=[]
    for v in vals:
        if "values" in v: nested+= [(v2.get("descriptor"),v2.get("id"),v.get("facetParameter")) for v2 in v["values"]]
        else: nested.append((v.get("descriptor"),v.get("id"),fp))
    hits=[x for x in nested if x[0] and ("ndia" in x[0] or "ANGALORE" in x[0].upper() or "Technology" in x[0] or "Data" in x[0] or "Product" in x[0])]
    print("::notice::FACET",fp,hits[:12])
