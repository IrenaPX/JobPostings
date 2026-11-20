import json, requests, sys
sys.path.insert(0, ".")
from src import scraper as s
from datetime import datetime
def gql(text, locale):
    p={"queryId":s.QUERY_ID,"variables":{"chatRequest":{"messages":[{"role":"user","content":[{"type":"text","text":text}]}],
      "thread_id":"probe"+datetime.utcnow().strftime('%H%M%S%f'),"channel":"job_search","context":{"job_search_context":{
      "locale":locale,"sort":"relevance","active_tab":"jobs","management_levels":[],"content_page":0,"future_roles_page":0,"job_page":0}}}},"headers":{}}
    try:
        d=requests.post(s.GRAPHQL_ENDPOINT,json=p,headers=s.HEADERS,timeout=20).json()
        tm=d.get("data",{}).get("jobSearchAssistant",{}).get("tool_messages",[])
        js=tm[0].get("artifact",{}).get("jobs",[]) if tm else []
        print("::notice::GQL",locale,repr(text),"->",[(j.get("country"),j.get("city"),j.get("jobPostingTitle"),j.get("job_id")) for j in js[:4]], "err" if "errors" in d else "")
    except Exception as e: print("::notice::GQL",locale,text,"EXC",str(e)[:150])
for loc in ["en_US","en_IN"]:
    gql("senior data scientist in Bengaluru, India",loc)
gql("software engineer jobs in India",'en_US')
# Workday
W="https://walmart.wd5.myworkdayjobs.com/wday/cxs/walmart/WalmartExternal/jobs"
try:
    r=requests.post(W,json={"appliedFacets":{},"limit":20,"offset":0,"searchText":"data scientist Bangalore"},headers={"Content-Type":"application/json","Accept":"application/json"},timeout=20)
    d=r.json()
    print("::notice::WD status",r.status_code,"total",d.get("total"),[ (j.get("title"),j.get("locationsText"),j.get("externalPath")) for j in d.get("jobPostings",[])[:5]])
    for f in d.get("facets",[]):
        if "ocation" in f.get("facetParameter",""):
            vals=[(v.get("descriptor"),v.get("id")) for v in f.get("values",[]) if "ndia" in str(v)]
            print("::notice::WD facet",f.get("facetParameter"),vals[:5])
except Exception as e: print("::notice::WD EXC",str(e)[:200])
