#pragma once

#include "pusher.h"

namespace pic {

/// Boris pusher with drag force
template<size_t D, size_t V>
class BorisPusherDrag :
  public Pusher<D,V>
{

  /// amount of drag asserted on particles
  public:
  double drag;

  void push_container( pic::ParticleContainer&, double cfl) override;
};

} // end of namespace pic
