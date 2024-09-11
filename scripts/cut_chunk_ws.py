import sys
from cloudvolume import CloudVolume
import chunk_utils as cu
from cut_chunk_common import load_data, cut_data, save_raw_data
from augment_affinity import warp_z, adjust_affinitymap, mask_affinity_with_semantic_labels
import os

def write_metadata(fn, size, boundaries, offset):
    with open(fn, "w") as f:
        f.write(" ".join([str(x) for x in size]))
        f.write("\n")
        f.write(" ".join([str(x) for x in boundaries]))
        f.write("\n")
        f.write(str(offset))

param = cu.read_inputs(sys.argv[1])
global_param = cu.read_inputs(os.environ['PARAM_JSON'])
bbox = param["bbox"]
aff_bbox = bbox[:]
aff_bbox[2] = warp_z(bbox[2])
aff_bbox[5] = aff_bbox[2] + (bbox[5] - bbox[2])
print(bbox)
print(aff_bbox)
boundary_flags = param["boundary_flags"]
offset = param["offset"]

paddingBefore = [1, 1, 1]
paddingAfter = [1, 1, 1]
aff = load_data(global_param['AFF_PATH'], mip=global_param['AFF_RESOLUTION'], fill_missing=global_param.get('AFF_FILL_MISSING', False))
aff_cutout = adjust_affinitymap(aff, aff_bbox, boundary_flags, paddingBefore, paddingAfter)

if "SEM_PATH" in global_param and global_param.get("SEMANTIC_WS", False):
    sem = load_data(global_param['SEM_PATH'], mip=global_param['AFF_RESOLUTION'], fill_missing=global_param.get('SEM_FILL_MISSING', False))
    aff_cutout = mask_affinity_with_semantic_labels(aff_cutout, sem, bbox, boundary_flags, paddingBefore, paddingAfter)

if 'ADJUSTED_AFF_PATH' in global_param:
    vol = CloudVolume(global_param['ADJUSTED_AFF_PATH'], mip=global_param['AFF_RESOLUTION'], cdn_cache=False)
    vol[bbox[0]:bbox[3], bbox[1]:bbox[4], bbox[2]:bbox[5], :] = aff_cutout[1:-1, 1:-1, 1:-1, :]

save_raw_data("aff.raw", aff_cutout)

write_metadata("param.txt", aff_cutout.shape[0:3], boundary_flags, offset)

fn = "remap/done_{}_{}.data".format(cu.chunk_tag(param['mip_level'],param['indices']), offset)
f = open(fn,"w")
f.close()
#upload data

