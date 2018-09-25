#pragma once

#include "bwd_lagrangian.h"

namespace vlv {


using namespace Eigen;


/// \brief back-substituting semi-Lagrangian adaptive advection solver with gravity
template<typename T, int D, int V>
class GravityAmrMomentumLagrangianSolver : 
  virtual public AmrMomentumLagrangianSolver<T,D,V> 
{

  public:

    T g0; // strength of gravity
    T Lx; // box size

    GravityAmrMomentumLagrangianSolver(
        T g0,
        T Lx
        ) :
      g0(g0), Lx(Lx)
    {};

    virtual ~GravityAmrMomentumLagrangianSolver() = default;

    typedef std::array<T, 3> vec;

    /// Gravity
    inline Vector3f other_forces(
        Vector3f& uvel,
        vlv::tools::Params<T>& params) 
    override
    {
      T gam  = std::sqrt(1.0 + uvel.dot(uvel));
      //std::cout << "using special other force at xloc=" << params.xloc << " gam=" << gam;
      //std::cout << " with g0=" << g0 << " and Lx=" << Lx << "\n";

      //Vector3f ret( -g0*gam*(2.0*params.xloc/Lx - 1.0), 0, 0); // flux tube
      Vector3f ret( -g0*gam*(params.xloc/Lx)/params.cfl, 0, 0); // atmosphere
      return ret;
    }

    /// Relativistic Lorentz force
    inline Vector3f lorentz_force(
        Vector3f& /*uvel*/,
        Vector3f& E,
        Vector3f& /*B*/,
        T qm,
        T cfl)
    override {
      //std::cout << "using special Lorentz force, otherwise same\n";
        
      // electrostatic push
      //
      // Boris scheme for b=0 translates to
      // u = (cfl*u_0 + e + e)/cfl = u_0 + E/cfl
      //
      // with halving taken into account in definition of Ex
      return -qm*E/cfl;
    }

};


} // end of namespace vlv