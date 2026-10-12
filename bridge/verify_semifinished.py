# -*- coding: utf-8 -*-
import os, sys, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)) + '/../scripts')
import sw_core, sw_sketch, sw_features, sw_sel

def new_block(sw):
    m=sw_core.new_part(sw)
    sw_sketch.start_sketch(m,'front')
    sw_sketch.corner_rectangle(m,0,0,0.030,0.020)
    sw_sketch.end_sketch(m)
    sk=sw_sketch.last_sketch_feature(m).Name
    sw_features.extrude_boss(m,sketch=sk,depth_m=0.010)
    return m

def try_one(name, fn):
    try:
        r=fn()
        print(name,'PASS',r, flush=True)
        return {'name':name,'status':'pass','detail':str(r)}
    except Exception as e:
        print(name,'FAIL',repr(e)[:200], flush=True)
        return {'name':name,'status':'fail','error':repr(e)[:200]}

out=[]
sw=sw_core.connect()
# variable fillet on block
m=new_block(sw)
out.append(try_one('fillet_variable', lambda: (lambda f: (f.Name, sw_core.feature_type(f)))(sw_features.fillet(m,0.001,edge_specs={'kind':'edge','type':'line','length_mm':30.0},fillet_type='variable'))))
# face fillet on block
m2=new_block(sw)
out.append(try_one('fillet_face', lambda: (lambda f: (f.Name, sw_core.feature_type(f)))(sw_features.fillet(m2,0.001,edge_specs={'kind':'plane','normal':[0,0,1]},fillet_type='face'))))
# full round fillet attempt
m3=new_block(sw)
def full():
    sw_core.clear_selection(m3)
    f=sw_features.full_round_fillet(m3,
        side_face_specs1={'kind':'plane','normal':[0,1,0]},
        center_face_spec={'kind':'plane','normal':[0,0,1]},
        side_face_specs2={'kind':'plane','normal':[0,-1,0]})
    return (f.Name, sw_core.feature_type(f))
out.append(try_one('fillet_full_round', full))
# flex on block
m4=new_block(sw)
out.append(try_one('flex_bending', lambda: (lambda f: (f.Name, sw_core.feature_type(f)))(sw_features.flex(m4,'bending',30))))
# AddMate4/5 smoke: use bridge_asm already open? open it
import sw_assembly_full
asm_path=r'\\wsl.localhost\Ubuntu-24.04\home\zjulin\ai+sw\sw-draw-skill\output\bridge_asm.SLDASM'
try:
    asm=sw_core.open_doc(sw, asm_path, doc_type=2)
    comps=sw_assembly_full.component_list(asm, top_level=False)
    c1,c2=comps[0],comps[-1]
    # choose first face entities by name Face<1>/Face<2> naive
    def mate_smoke():
        mate,err=sw_assembly_full.add_mate_full(asm,c1,c2,'coincident',lock_rotation=True,width_option=0)
        return {'mate_ok': mate is not None, 'err': err, 'mate_count': len(sw_assembly_full.list_mates(asm))}
    out.append(try_one('add_mate4_5_smoke', mate_smoke))
except Exception as e:
    out.append({'name':'add_mate4_5_smoke','status':'fail','error':repr(e)[:200]})

report_path=r'\\wsl.localhost\Ubuntu-24.04\home\zjulin\ai+sw\sw-draw-skill\docs\reports\semifinished_report.json'
with open(report_path,'w',encoding='utf-8') as f:
    json.dump({'results':out},f,ensure_ascii=False,indent=2)
print('report',report_path, flush=True)
