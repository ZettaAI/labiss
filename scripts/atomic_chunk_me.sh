#!/bin/bash
set -euo pipefail
INIT_PATH="$(dirname "$0")"
. ${INIT_PATH}/init.sh $1
output_chunk=`basename $1 .json`
output_path=out/agg
try acquire_cpu_slot

just_in_case rm -rf remap
just_in_case rm -rf chunked_rg
just_in_case rm -rf ${output_path}

try mkdir remap
try mkdir chunked_rg

try mkdir -p ${output_path}/{info,scratch}

for d in $META; do
    echo "create $d"
    just_in_case rm -rf $d
    try mkdir $d
done

try python3 $SCRIPT_PATH/merge_chunkmap.py $1

try taskset -c $cpuid python3 $SCRIPT_PATH/cut_chunk_agg.py $1
try taskset -c $cpuid $BIN_PATH/acme param.txt $output_chunk
try mv edges_"$output_chunk".data input_rg.data

for i in {0..5}
do
    try cat boundary_"$i"_"$output_chunk".data >> frozen.data
done

try touch ns.data
try touch ongoing_semantic_labels.data

if [ "$OVERLAP" = "1" ]; then
    try taskset -c $cpuid $BIN_PATH/agg_nonoverlap $PARAM_JSON input_rg.data frozen.data ns.data
else
    try taskset -c $cpuid $BIN_PATH/agg $PARAM_JSON input_rg.data frozen.data ns.data
fi

try cat remap.data >> localmap.data
try taskset -c $cpuid $BIN_PATH/split_remap chunk_offset.txt $output_chunk
try taskset -c $cpuid $BIN_PATH/assort $output_chunk $META

try mv done_segments.data ${output_path}/info/info_"$output_chunk".data
try mv done_sem.data ${output_path}/info/semantic_labels_"$output_chunk".data
try mv done_size.data ${output_path}/info/seg_size_"$output_chunk".data
try mv sem_cuts.data ${output_path}/info/sem_rejected_edges_"$output_chunk".log
try mv rejected_edges.log ${output_path}/info/size_rejected_edges_"$output_chunk".log
try mv twig_edges.log ${output_path}/info/twig_edges_"$output_chunk".log
try mv chunked_rg ${output_path}
try mv remap ${output_path}

try mv residual_rg.data residual_rg_"$output_chunk".data
try mv ongoing_segments.data ongoing_supervoxel_counts_"$output_chunk".data
try mv ongoing_sem.data ongoing_semantic_labels_"$output_chunk".data
try mv ongoing_size.data ongoing_seg_size_"$output_chunk".data

if [ "$PARANOID" = "1" ]; then
    try md5sum *_"${output_chunk}".data > ${output_path}/scratch/"${output_chunk}".data.md5sum
fi

try tar -cvf - *_"${output_chunk}".data | $COMPRESS_CMD > ${output_path}/scratch/"${output_chunk}".tar."${COMPRESSED_EXT}"

for d in $META; do
    if [ "$(ls -A $d)"  ]; then
        try $UPLOAD_CMD $d $FILE_PATH/
    fi
done

retry 10 $UPLOAD_CMD "${output_path}" $IO_SCRATCH_PATH/

try rm -rf chunked_rg
try rm -rf remap
try rm -rf ${output_path}

for d in $META; do
    try rm -rf $d
done

try release_cpu_slot
