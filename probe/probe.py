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
for t in ["(IND) senior data scientist","(IND) SENIOR, DATA SCIENTIST","IND staff software engineer","(IND) senior product manager"]:
    gql(t,"en_US")
H={"Content-Type":"application/json","Accept":"application/json","User-Agent":s.HEADERS["User-Agent"],"Origin":"https://walmart.wd5.myworkdayjobs.com","Referer":"https://walmart.wd5.myworkdayjobs.com/WalmartExternal"}
for site in ["WalmartExternal","walmartexternal"]:
    W="https://walmart.wd5.myworkdayjobs.com/wday/cxs/walmart/"+site+"/jobs"
    try:
        r=requests.post(W,json={"appliedFacets":{},"limit":20,"offset":0,"searchText":"IND data scientist"},headers=H,timeout=20)
        print("::notice::WD",site,r.status_code,r.text[:300].replace("\n"," "))
    except Exception as e: print("::notice::WD EXC",str(e)[:200])
