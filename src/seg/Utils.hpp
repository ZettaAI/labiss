#ifndef UTILS_HPP
#define UTILS_HPP

#include "Types.h"
#include "SlicedOutput.hpp"
#include <queue>
#include <fstream>
#include <iostream>
#include <boost/format.hpp>
#include <sys/stat.h>

size_t filesize(const std::string & filename)
{
    struct stat stat_buf;
    int rc = stat(filename.c_str(), &stat_buf);
    return rc == 0 ? stat_buf.st_size : 0;
}


template <class T>
std::vector<T> read_array(const std::string & filename)
{
    std::vector<T> array;

    std::cout << "filesize:" << filename << ", " <<  filesize(filename)/sizeof(T) << std::endl;
    size_t data_size = filesize(filename);
    if (data_size % sizeof(T) != 0) {
        std::cerr << "File incomplete!: " << filename << std::endl;
        std::abort();
    }

    FILE* f = std::fopen(filename.c_str(), "rbXS");
    if ( !f ) {
        std::cerr << "Cannot open the input file" << std::endl;
        std::abort();
    }

    size_t array_size = data_size / sizeof(T);

    array.resize(array_size);
    std::size_t nread = std::fread(array.data(), sizeof(T), array_size, f);
    if (nread != array_size) {
        std::cerr << "Reading: " << nread << " entries, but expecting: " << array_size << std::endl;
        std::abort();
    }
    std::fclose(f);

    return array;
}


template<typename T>
MapContainer<T,T> loadChunkMap(const char * filename)
{
    MapContainer<T, T> map;
    std::ifstream cm_file(filename);
    if (!cm_file.is_open()) {
        std::cout << "Cannot open the supervoxel count file" << std::endl;
        std::abort();
    }

    T k,v;
    while (cm_file.read(reinterpret_cast<char *>(&k), sizeof(k))) {
           cm_file.read(reinterpret_cast<char *>(&v), sizeof(v));
           map[k] = v;
    }
    std::cout << "load " << map.size() << " chunk map entries" << std::endl;
    return map;
}


std::vector<ContactRegion> connectComponent(const ContactRegion & cr)
{
    std::vector<ContactRegion> cc_sets;
    ContactRegion visited;
    for (auto root: cr) {
        if (visited.count(root) > 0) {
            continue;
        }
        ContactRegion cc;
        std::queue<Coord> voxel_queue;
        voxel_queue.push(root);
        while (!voxel_queue.empty()) {
            auto node = voxel_queue.front();
            voxel_queue.pop();
            if (visited.count(node) > 0) {
                continue;
            }
            visited.insert(node);
            cc.insert(node);
            for (int i = -1; i <= 1; i++) {
                for (int j = -1; j <= 1; j++) {
                    for (int k = -1; k <= 1; k++) {
                        if (i == 0 && j == 0 && k == 0) {
                            continue;
                        }
                        Coord neighbor({node[0]+i,node[1]+j,node[2]+k});
                        if (visited.count(neighbor) == 0 && cr.count(neighbor) > 0) {
                            voxel_queue.push(neighbor);
                        }
                    }
                }
            }
        }
        cc_sets.push_back(cc);
    }
    return cc_sets;
}


template <int skipType, typename Ts, typename ... Ta>
void traverseSegments(const Ts& seg, Ta& ... extractors)
{
    auto base = seg.index_bases();
    auto shape = seg.shape();
    auto c = Coord({0,0,0});

    constexpr auto scan_grid = std::array<std::array<int, 3>, 3> {{
                            {-1,0,0}, {0,-1,0}, {0,0,-1},
    }};

    constexpr std::array<int, 3> aff_backward = {1, 1, 1}
    constexpr std::array<int, 3> aff_forward = {0, 0, 0};

    int z = skipType == 2 ? base[2]+1: base[2];
    for (; z != base[2]+shape[2]; z++) {
        c[2] = z;
        int y = skipType == 2 ? base[1]+1: base[1];
        for (; y != base[1]+shape[1]; y++) {
            c[1] = y;
            int x = skipType == 2 ? base[0]+1: base[0];
            for (; x != base[0]+shape[0]; x++) {
                if (seg[x][y][z] == 0) {
                    continue;
                }
                c[0] = x;
                for (int i = 0; i < 3; i++) {
                    if (c[i] < base[i] + aff_backward[i] + aff_forward[i]) {
                        (extractors.collectBoundary(i, c, seg[x][y][z]), ...);
                    }
                    if (c[i] >= (base[i] + shape[i] - aff_backward[i] - aff_forward[i])) {
                        (extractors.collectBoundary(i+3, c, seg[x][y][z]), ...);
                    }
                }
                if (skipType == 1) { //Overlap in forward directions, skip overlapping volume
                    bool shouldSkip = false;
                    for (int i = 0; i < 3; i++) {
                        if (c[i] < base[i] + aff_backward[i] or c[i] >= (base[i] + shape[i] - aff_forward[i])) {
                            shouldSkip = true;
                        }
                    }
                    if (shouldSkip) {
                        continue;
                    }
                }
                (extractors.collectVoxel(c, seg[x][y][z]), ...);
                for (size_t i = 0; i < scan_grid.size(); i++) {
                    const auto & p = scan_grid[i];
                    const auto s = seg[x+p[0]][y+p[1]][z+p[2]];
                    if (s != 0 and seg[x][y][z] != s) {
                        (extractors.collectContactingSurface(i, c, seg[x][y][z], s), ...);
                    }
                }
            }
        }
    }
}

template <typename Ts, typename Tp>
void chunkedOutput(const MapContainer<Ts,Tp> & data, const std::string & prefix, const std::string & tag, size_t ac_offset) {
    SlicedOutput<std::pair<Ts, Tp>, Ts> chunked_output(str(boost::format("%1%_%2%.data") % prefix % tag));
    size_t current_ac1 = std::numeric_limits<std::size_t>::max();

    std::vector<std::pair<Ts, Tp> > sorted_data(std::begin(data), std::end(data));
    std::sort(std::begin(sorted_data), std::end(sorted_data), [ac_offset](auto & a, auto & b) {
         return a.first < b.first;
    });

    for (const auto & [k, v] : sorted_data) {
        if (current_ac1 != (k - (k % ac_offset))) {
            chunked_output.flushChunk(current_ac1);
            current_ac1 = k - (k % ac_offset);
        }

        chunked_output.addPayload(std::make_pair(k, v));
    }
    chunked_output.flushChunk(current_ac1);
    chunked_output.flushIndex();
}

#endif
