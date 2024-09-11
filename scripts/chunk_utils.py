import json
import os
import shutil

bits_per_dim = 10
n_bits_for_layer_id = 8

chunk_voxels = 1 << (64-n_bits_for_layer_id-bits_per_dim*3)

def get_chunk_offset(layer=None, x=None, y=None, z=None):
        """ (1) Extract Chunk ID from Node ID
            (2) Build Chunk ID from Layer, X, Y and Z components
        :param layer: int
        :param x: int
        :param y: int
        :param z: int
        :return: np.uint64
        """

        if not(x < 2 ** bits_per_dim and
               y < 2 ** bits_per_dim and
               z < 2 ** bits_per_dim):
            raise Exception("Chunk coordinate is out of range for"
                            "this graph on layer %d with %d bits/dim."
                            "[%d, %d, %d]; max = %d."
                            % (layer, bits_per_dim, x, y, z,
                               2 ** bits_per_dim))

        layer_offset = 64 - n_bits_for_layer_id
        x_offset = layer_offset - bits_per_dim
        y_offset = x_offset - bits_per_dim
        z_offset = y_offset - bits_per_dim
        return (layer << layer_offset | x << x_offset |
                         y << y_offset | z << z_offset)


def read_inputs(fn):
    with open(fn) as f:
        return json.load(f)

def chunk_tag(mip_level, indices):
    idx = [mip_level] + indices
    return "_".join([str(i) for i in idx])

def parent(indices):
    return [i//2 for i in indices]

# 0: -x-axis, 1: -y-axis, 2: -z-axis, 3: +x-axis, 4: +y-axis, 5: +z-axis
def generate_subface_keys(idx):
    pos = idx % 3
    offset = idx // 3
    faces = [[i,j] for i in range(2) for j in range(2)]
    list(map(lambda l: l.insert(pos, offset), faces))
    return ["_".join([str(i) for i in l]) for l in faces]

def generate_superface_keys(idx):
    pos = idx % 3
    offset = -1 + idx // 3 * 2
    faces = [[i,j] for i in range(-1,2,1) for j in range(-1,2,1)]
    list(map(lambda l: l.insert(pos, offset), faces))
    return ["_".join([str(i) for i in l]) for l in faces]

def generate_vanished_subface():
    return {"_".join([str(x) for x in [i,j,k]]): [3-3*i,4-3*j,5-3*k] for i in range(2) for j in range(2) for k in range(2)}

def merge_files(target, fnList):
    if len(fnList) == 1:
        if os.path.exists(fnList[0]):
            os.rename(fnList[0],target)
        else:
            open(target, 'a').close()
        return

    with open(target,"wb") as outfile:
        for fn in fnList:
            try:
                shutil.copyfileobj(open(fn, 'rb'), outfile)
            except IOError as e:
                print(fn, " does not exist")
                raise e

    for fn in fnList:
        try:
            os.remove(fn)
        except IOError as e:
            print(fn, " does not exist")
            raise e

def lift_intermediate_outputs(p, prefix):
    d = p["children"]
    mip_c = p["mip_level"]-1
    inputs = [prefix+"_"+chunk_tag(mip_c, d[k])+".data" for k in d]
    output = prefix+"_"+chunk_tag(p["mip_level"], p["indices"])+".data"
    merge_files(output, inputs)

def merge_intermediate_outputs(p, prefix):
    d = p["children"]
    mip_c = p["mip_level"]-1
    inputs = [prefix+"_"+chunk_tag(mip_c, d[k])+".data" for k in d]
    output = prefix+".data"
    merge_files(output, inputs)

def generate_ancestors(f, target=None, ceiling=None):
    p = read_inputs(f)
    top_mip = p["top_mip_level"]
    if ceiling is not None:
        top_mip = ceiling
    mip = p["mip_level"]
    indices = p["indices"]
    ancestor = [chunk_tag(mip, indices)]
    while mip < top_mip:
        mip += 1
        indices = parent(indices)
        if target is None or mip == target:
            ancestor.append(chunk_tag(mip, indices))

    return ancestor

def generate_siblings(f):
    param = read_inputs(f)
    indices = param["indices"]
    mip = param["mip_level"]
    boundary_flags = param["boundary_flags"]

    volume = [[0,0,0]]
    faces = []
    edges = []
    vertices = []
    for j, f in enumerate(boundary_flags):
        if j < 3:
            i = j
            offset = -1
        else:
            i = j - 3
            offset = 1

        if f == 0:
            new_faces = [volume[0][:]]
            new_faces[0][i] += offset
            new_edges = []
            for a in faces:
                c = a[:]
                c[i] += offset
                new_edges.append(c)
            new_vertices = []
            for b in edges:
                c = b[:]
                c[i] += offset
                new_vertices.append(c)
            faces+=new_faces
            edges+=new_edges
            vertices+=new_vertices

    return mip, indices, volume, faces, edges, vertices

def touch_done_files(f, tag):
    d = generate_descedants(f,target=0)
    path = os.path.dirname(f)
    with open("done_remap.txt","w") as f:
        for c in d:
            cp = read_inputs(os.path.join(path,c+".json"))
            fn_done = "remap/done_{}_{}.data".format(tag, cp["offset"])
            open(fn_done,'a').close()
            f.write("{}\n".format(fn_done))
            fn_small = "remap/size_{}_{}.data".format(tag, cp["offset"])
            open(fn_small,'a').close()
            f.write("{}\n".format(fn_small))


def generate_descedants(f, target=None):
    path = os.path.dirname(f)
    p = read_inputs(f)
    mip = p["mip_level"]
    if mip == 0:
        return []
    else:
        mip_c = mip - 1
        d = p["children"]
        descedants = []
        for k in d:
            tag = chunk_tag(mip_c, d[k])
            if target is None or mip_c == target:
                descedants.append(tag)

        for k in d:
            tag = chunk_tag(mip_c, d[k])
            f_c = os.path.join(path, tag+".json")
            descedants += generate_descedants(f_c, target)

        return descedants


def download_slice(prefix, tag, offset):
    from cloudfiles import CloudFiles
    import binascii
    import numpy as np
    chunkid = np.uint64(offset)
    cf = CloudFiles(os.path.join(os.environ['SCRATCH_PATH'], os.environ['STAGE']))
    header = cf[f'{prefix}_{tag}.data', 0:20]
    print(header[:4])
    idx_info = np.frombuffer(header[4:],dtype='uint64')
    if idx_info[1] == 4:
        return None
    idx_content = cf[f'{prefix}_{tag}.data', idx_info[0]:idx_info[0]+idx_info[1]]
    assert np.frombuffer(idx_content[-4:], dtype='uint32')[0] == binascii.crc32(idx_content[:-4])
    idx_dt = np.dtype([('chunkid', np.uint64), ('offset', np.uint64), ('bytesize',np.uint64)])
    idx_payload = np.frombuffer(idx_content[:-4], dtype=idx_dt)
    idx = np.searchsorted(idx_payload['chunkid'], chunkid)
    print("index:", idx)
    print(offset)
    print("total len:", len(idx_payload))
    #print(idx_payload)
    if idx == len(idx_payload):
        return None
    chunk = idx_payload[idx]
    print(chunk)
    if chunkid != chunk['chunkid']:
        print(f"Cannot find {chunkid}")
        return None
    else:
        payload = cf[f'{prefix}_{tag}.data', chunk['offset']:chunk['offset']+chunk['bytesize']]
        assert np.frombuffer(payload[-4:], dtype='uint32')[0] == binascii.crc32(payload[:-4])
        return payload[:-4]
