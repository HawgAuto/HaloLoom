#!/usr/bin/env python3
"""Fail-closed raw rocprof counter ownership reducer.

Selects only rows whose device interval is wholly inside the controller's exact
rocprofiler_get_timestamp / CLOCK_BOOTTIME HTTP bracket and whose Process_Id has one stable pre/post
/proc identity. Raw CSVs remain immutable and are hash-bound in the result.
"""
from __future__ import annotations
import argparse,csv,hashlib,json,math,os
from pathlib import Path
HEADER=["Correlation_Id","Dispatch_Id","Agent_Id","Queue_Id","Process_Id","Thread_Id","Grid_Size","Kernel_Id","Kernel_Name","Workgroup_Size","LDS_Block_Size","Scratch_Size","VGPR_Count","Accum_VGPR_Count","SGPR_Count","Counter_Name","Counter_Value","Start_Timestamp","End_Timestamp"]

def need(v,msg):
    if not v: raise ValueError(msg)
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def strict_json(p):
    def pairs(xs):
        d={}
        for k,v in xs: need(k not in d,f"duplicate JSON key {k}");d[k]=v
        return d
    def constant(x): raise ValueError(f"nonfinite JSON {x}")
    return json.loads(p.read_text(),object_pairs_hook=pairs,parse_constant=constant)
def integer(v,name,positive=False):
    need(v and v.isascii() and v.isdigit(),f"invalid {name}"); x=int(v)
    need(not positive or x>0,f"nonpositive {name}"); return x

def main():
    ap=argparse.ArgumentParser();ap.add_argument("--lifecycle",required=True);ap.add_argument("--raw",action="append",required=True);ap.add_argument("--output",required=True);ap.add_argument("--agent",default="Agent 1");a=ap.parse_args()
    life_path=Path(a.lifecycle); life=strict_json(life_path)
    need(life.get("schema")=="qwen38_metrix_lifecycle.v1" and life.get("status")=="COMPLETE","lifecycle not complete")
    need(life.get("clock")=="CLOCK_MONOTONIC_RAW" and life.get("server_reaped") is True,"wrong clock or unreaped server")
    req=life.get("request");need(type(req) is dict,"missing request bracket")
    sdk=req.get("sdk_clock");need(type(sdk) is dict,"missing recorded SDK clock bracket")
    need(sdk.get("source")=="rocprofiler_get_timestamp" and sdk.get("clock")=="CLOCK_BOOTTIME","unproven SDK clock domain")
    need(sdk.get("sdk_sha256")=="9280eae676a8d3d135096a327a2524b2b50a9146b13d850c626e0d8e0e49b7b8","wrong SDK clock library identity")
    start=sdk.get("start_ns");end=sdk.get("end_ns")
    need(type(start) is int and type(end) is int and 0<start<end,"bad request bracket")
    def identities(rows):
        need(type(rows) is list and rows,"missing process snapshot")
        out={}
        for x in rows:
            need(type(x) is dict and type(x.get("pid")) is int and type(x.get("start_ticks")) is int,"bad process identity")
            need(x["pid"] not in out,"duplicate pid snapshot");out[x["pid"]]=x["start_ticks"]
        return out
    pre=identities(req.get("pre_processes"));post=identities(req.get("post_processes"))
    stable={pid:tick for pid,tick in pre.items() if post.get(pid)==tick}
    need(life.get("server_pid") in stable,"server identity not stable across request")
    selected=[]; outside=0; seen=set(); raw_manifest=[]
    for name in a.raw:
        p=Path(name);need(p.is_file() and p.stat().st_size>0,f"missing/empty raw CSV {p}")
        raw_manifest.append({"path":str(p.resolve()),"size":p.stat().st_size,"sha256":sha(p)})
        with p.open("r",encoding="utf-8",newline="") as f:
            reader=csv.reader(f,strict=True); hdr=next(reader,None);need(hdr==HEADER,f"wrong raw header {p}")
            for line,row in enumerate(reader,2):
                need(len(row)==len(HEADER),f"ragged row {p}:{line}");r=dict(zip(HEADER,row))
                pid=integer(r["Process_Id"],"Process_Id",True);st=integer(r["Start_Timestamp"],"Start_Timestamp",True);en=integer(r["End_Timestamp"],"End_Timestamp",True)
                need(st<en,"inverted counter interval")
                need(r["Counter_Name"]=="OccupancyPercent","unexpected counter")
                need(r["Agent_Id"]==a.agent,"unexpected GPU agent")
                need(bool(r["Kernel_Name"]),"empty kernel name")
                try: val=float(r["Counter_Value"])
                except ValueError: raise ValueError("invalid counter value")
                need(math.isfinite(val),"nonfinite counter value")
                key=(pid,r["Dispatch_Id"],r["Counter_Name"],st,en,r["Kernel_Name"])
                need(key not in seen,"duplicate raw counter row");seen.add(key)
                if pid in stable and start<=st and en<=end:
                    selected.append({"source":str(p.resolve()),"line":line,**r,"Counter_Value":val,"Start_Timestamp":st,"End_Timestamp":en,"Process_Id":pid,"Process_Start_Ticks":stable[pid]})
                else: outside+=1
    need(selected,"zero strictly request-owned counter rows")
    selected.sort(key=lambda r:(r["Start_Timestamp"],r["End_Timestamp"],r["Process_Id"],r["Dispatch_Id"],r["Kernel_Name"]))
    result={"schema":"qwen38_metrix_raw_ownership.v1","status":"PASS","timing_authority":False,"ownership_basis":"rocprofiler_get_timestamp CLOCK_BOOTTIME interval containment + stable pre/post process identity","lifecycle":{"path":str(life_path.resolve()),"sha256":sha(life_path),"request_start_ns":start,"request_end_ns":end,"response_id":req.get("response_id")},"raw_csvs":raw_manifest,"selected_rows":selected,"selected_count":len(selected),"out_of_scope_count":outside,"claims":{"actual_full_model_counter_rows":True,"request_owned":True,"performance":False,"decode_exclusive_symbol":False,"exact_replay":False,"optimizer_ready":False}}
    out=Path(a.output);out.parent.mkdir(parents=True,exist_ok=True);tmp=out.with_suffix(out.suffix+".tmp");tmp.write_text(json.dumps(result,sort_keys=True,indent=2)+"\n");os.replace(tmp,out)
if __name__=="__main__": main()
