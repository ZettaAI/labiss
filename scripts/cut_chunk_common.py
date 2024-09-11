from cloudvolume import CloudVolume
import chunk_utils as cu
import numpy
import os


def load_data(url, **kwargs):
    print("cloud volume url: ", url)

    return CloudVolume(url, cache=False, **kwargs)
    #return CloudVolumeGSUtil(url, fill_missing=True)

def load_gt_data(url, mip=0):
    print("cloud volume url: ", url)
    print("mip level: ", mip)

    return CloudVolume(url, fill_missing=True, bounded=False, mip=mip)

def save_raw_data(fn, data):
    f = numpy.memmap(fn, dtype=data.dtype, mode='w+', order='F', shape=data.shape)
    f[:] = data[:]
    del f

def pad_data(data, padding):
    pad = [[padding[i], padding[i+3]] for i in range(3)]
    if len(data.shape) == 3:
        return numpy.pad(data, pad, 'constant', constant_values=0)
    elif len(data.shape) == 4:
        return numpy.pad(data, pad+[[0,0]], 'constant', constant_values=0)
    else:
        raise RuntimeError("encountered array of dimension " + str(len(data.shape)))

def convert_and_scale_integer_data(data, dtype_out):
    if numpy.issubdtype(data.dtype, numpy.integer):
        print(f"convert {data.dtype} to {dtype_out}")
        info = numpy.iinfo(data.dtype)
        return (data.astype(dtype_out, order='F') - info.min)/(info.max - info.min)
    else:
        return data

def cut_data(data, start_coord, end_coord, padding):
    bb = tuple(slice(start_coord[i], end_coord[i]) for i in range(3))
    global_param = cu.read_inputs(os.environ['PARAM_JSON'])
    if data.shape[3] == 1:
        if data.dtype == 'float32':
            pmap = numpy.squeeze(data[bb])
            affinity = [numpy.minimum(numpy.roll(pmap, shift=1, axis=axis), pmap) for axis in range(3)]
            return pad_data(numpy.stack(affinity, axis=-1), padding)
        else:
            return pad_data(data[bb], padding)
    elif data.shape[3] == 3:
        return pad_data(convert_and_scale_integer_data(data[bb+(slice(0,3),)], "float32"), padding)
    elif data.shape[3] == 4: #0-2 affinity, 3 myelin
        th = global_param.get('MYELIN_THRESHOLD', 0.3)
        print("threshold myelin mask at {}".format(th))
        cutout = data[bb+(slice(0,4),)]
        affinity = cutout[:,:,:,0:3]
        myelin = cutout[:,:,:,3]
        mask = myelin > th
        for i in range(3):
            tmp = affinity[:,:,:,i]
            tmp[mask] = 0
            #affinity[:,:,:,i] = numpy.multiply(affinity[:,:,:,i]*(1-myelin))
        return pad_data(affinity, padding)
    else:
        aff_channels = global_param.get('AFF_CHANNELS', 3)
        if data.shape[3] >= aff_channels:
            return pad_data(convert_and_scale_integer_data(data[bb+(slice(0,aff_channels),)], "float32"), padding)
        raise RuntimeError("encountered array of dimension " + str(len(data.shape)))


