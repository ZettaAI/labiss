import sys
from chunk_utils import read_inputs
from cut_chunk_common import load_data, cut_data, save_raw_data
from augment_affinity import adjust_affinitymap, warp_z
import os

def chunk_origin(bbox):
    offset = bbox[0:3]
    for i in range(3):
        if boundary_flags[i] == 1:
            offset[i] -= 1
    return offset

def write_metadata(fn, offset, size, ac_offset):
    with open(fn, "w") as f:
        f.write(" ".join([str(x) for x in offset]))
        f.write("\n")
        f.write(" ".join([str(x) for x in size]))
        f.write("\n")
        f.write(str(ac_offset))

param = read_inputs(sys.argv[1])
global_param = read_inputs(os.environ['PARAM_JSON'])
bbox = param["bbox"]
aff_bbox = bbox[:]
aff_bbox[2] = warp_z(bbox[2])
aff_bbox[5] = aff_bbox[2] + (bbox[5] - bbox[2])
print(bbox)
print(aff_bbox)
ac_offset = param["ac_offset"]
boundary_flags = param["boundary_flags"]

extra_aff_backward = [1, 1, 1]
extra_aff_forward = [0, 0, 0]

extra_aff_before = [0, 0, 0]
extra_aff_after = [x + y for x, y in zip(extra_aff_backward, extra_aff_forward)]
padding_boundary = extra_aff_after + extra_aff_after

aff = load_data(global_param['AFF_PATH'], mip=global_param['AFF_RESOLUTION'], fill_missing=global_param.get('AFF_FILL_MISSING', False))
aff_cutout = adjust_affinitymap(aff, aff_bbox, boundary_flags, extra_aff_before, extra_aff_after, padding_boundary)

save_raw_data("aff.raw", aff_cutout)
del aff_cutout

start_coord = [bbox[i]-(1-boundary_flags[i])*extra_aff_before[i] for i in range(3)] # Should equals to bbox[0:3]
end_coord = [bbox[i+3]+(1-boundary_flags[i+3])*extra_aff_after[i] for i in range(3)]
padding = [x*y for x, y in zip(padding_boundary, boundary_flags)]

seg = load_data(os.environ['WS_PATH'], mip=global_param['AFF_RESOLUTION'], fill_missing=global_param.get('WS_FILL_MISSING', False))
seg_cutout = cut_data(seg, start_coord, end_coord, padding)
save_raw_data("seg.raw", seg_cutout)

if "SEM_PATH" in global_param:
    sem = load_data(global_param['SEM_PATH'], mip=global_param['AFF_RESOLUTION'], fill_missing=global_param.get('SEM_FILL_MISSING', False))
    sem_cutout = cut_data(sem, start_coord, end_coord, padding)
    save_raw_data("sem.raw", sem_cutout)

#save_data("aff.h5", aff_cutout)
#save_data("seg.h5", seg_cutout)

write_metadata("param.txt", chunk_origin(bbox), seg_cutout.shape[0:3], ac_offset)
with open("chunk_offset.txt", "w") as f:
    f.write(str(ac_offset))
