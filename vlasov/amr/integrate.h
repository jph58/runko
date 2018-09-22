#pragma once

#include "mesh.h"


/// integrate Adaptive Mesh phase space with function Chi(u)
// TODO: think about merging with amr_spatial_solver auxiliary functions
template<typename T, typename Lambda>
T integrate_moment(
    const toolbox::AdaptiveMesh<T,3>& m,
    Lambda&& chi
    ) {
  auto integ = T(0);

  // pre-create size of the elements
  // TODO optimize this depending on top_refinement_level
  //std::vector<T> du;
  //du.resize( m.top_refinement_level+1 );
  int rfl; // current refinement level
  //for(rfl=0; rfl<=m.top_refinement_level; rfl++) {
  //  auto lens = m.get_length(rfl);
  //  T len = lens[0]*lens[1]*lens[2];
  //  du[rfl] = len;
  //}

  // simplified approach assuming no refinement.
  // TODO: rewrite this to accommodate adaptivity
  auto lens = m.get_length(0);
  T du0 = lens[0]*lens[1]*lens[2];


  // convolve with chi(u) function
  for(auto cid : m.get_cells(false) ) {
    if( !m.is_leaf(cid) ) continue; //TODO: fixme

    auto index = m.get_indices(cid);
    rfl        = m.get_refinement_level(cid);
    auto uvel  = m.get_center(index, rfl);

    //std::cout << "cid:" << cid << " data:" << m.data.at(cid) << " du:" << du[rfl] << " chi:" << chi(uvel) << '\n';
    //std::cout << "cid:" << cid << " data:" << m.get(cid) << " du:" << du[rfl] << " chi:" << chi(uvel) << '\n';

    //integ += m.data.at(cid) * du[rfl] * chi(uvel);
    //integ += m.data.at(cid) * du[rfl] * chi(uvel);
    integ += m.data.at(cid) * du0 * chi(uvel);
  }

  return integ;
}


