from __future__ import print_function
from mpi4py import MPI

import numpy as np
import sys, os
import h5py

from pyrunko.ffe import set_step
import pyrunko.ffe.twoD as pyffe
import pycorgi.twoD as corgi
import pyrunko.vlv.twoD as pyvlv
import pyrunko.fields.twoD as pyfld

from timer import Timer

#from configSetup import Configuration
from init_problem import Configuration_Reconnection as Configuration
import argparse
import initialize as init
from initialize_ffe import loadTiles, initialize_virtuals
from initialize_pic import globalIndx


from visualize import get_yee
try:
    import matplotlib.pyplot as plt
    from visualize import plotNode
    from visualize import plotJ, plotE
    from visualize import saveVisz
    
    from visualize import getYee2D
    from visualize import plot2dYee
except:
    pass

from numpy import sinh, cosh, tanh, pi, sin, cos, tan, sqrt

from antenna2 import Antenna


# Field initialization (guide field)
def insert_em(grid, conf):

    kk = 0
    for tile in tiles_all(grid): 
        yee = tile.get_yee(0)

        ii,jj = tile.index
        for n in range(conf.NzMesh):
            for m in range(-3, conf.NyMesh+3):
                for l in range(-3, conf.NxMesh+3):
                    
                    # FIXME
                    #print("{}: ind ({},{},{})".format(grid.rank(), l,m,n))
                    # get global coordinates
                    iglob, jglob, kglob = globalIndx( (ii,jj), (l,m,n), conf)

                    yee.ex[l,m,n] = 0.0
                    yee.ey[l,m,n] = 0.0
                    yee.ez[l,m,n] = 0.0

                    yee.bx[l,m,n] = 0.0
                    yee.by[l,m,n] = 0.0
                    yee.bz[l,m,n] = conf.binit   

# Field initialization   
def insert_guide_field(grid, conf):
    binit = conf.binit #initial B_0

    kk = 0
    for jj in range(grid.get_Ny()):
        for ii in range(grid.get_Nx()):
            if grid.get_mpi_grid(ii,jj) == grid.rank():
                c = grid.get_tile(ii,jj)
                yee = c.get_yee(0)

                for n in range(conf.NzMesh):
                    for m in range(conf.NyMesh):
                        for l in range(conf.NxMesh):

                            # get global coordinates
                            iglob, jglob, kglob = globalIndx( (ii,jj), (l,m,n), conf)

                            yee.bz[l,m,n] = binit



# Field initialization   
def insert_em_harris_sheet(grid, conf):

    delta       = conf.sheet_thickness/(2.0*pi) #sheet thickness incl. 2pi 
    pinch_delta = conf.pinch_width/(2.0*pi)     #pinch thickness incl. 2pi
    eta  = conf.sheet_density 
    beta = 0.0 #conf.beta #sheet bulk flow; NOTE: for force-free setup no flow
    sigma = conf.sigma #magnetization


    #binit  = conf.binit
    #btheta = conf.btheta
    #bphi   = conf.bphi

    do_3D = False

    #note: if periodicx then mxhalf is 1/4 of Lx else 1/2
    mxhalf  = conf.mxhalf
    myhalf  = conf.myhalf
    mzhalf  = conf.mzhalf

    lstripe = conf.lstripe #FIXME del
    Lx      = conf.lstripe

    binit = conf.binit #initial B_0

    kk = 0
    for jj in range(grid.get_Ny()):
        for ii in range(grid.get_Nx()):
            if grid.get_mpi_grid(ii,jj) == grid.rank():
                c = grid.get_tile(ii,jj)
                yee = c.get_yee(0)

                for n in range(conf.NzMesh):
                    for m in range(conf.NyMesh):
                        for l in range(conf.NxMesh):

                            # get global coordinates
                            iglob, jglob, kglob = globalIndx( (ii,jj), (l,m,n), conf)

                            # trigger field modulation in z coordinate
                            if do_3D:
                                triggerz = cosh((kglob - mzhalf)/pinch_delta) #3D
                            else:
                                triggerz = 1.0

                            # flipping harris sheet stripe
                            if not(conf.periodicx):
                                stripetanh = tanh((iglob-mxhalf)/delta)
                            else:
                                stripetanh = tanh(Lx*sin(2.*pi*(iglob - mxhalf)/Lx)/delta/2.0/pi)

                            #FIXME

                            #plasma bulk velocity modulation factor; 
                            #NOTE: true velocity v/c= velstripe*beta

                            #velstripe = tanh((iglob-mxhalf)/pinch_delta)/cosh((iglob-mxhalf)/pinch_delta)
                            #velstripe = tanh((iglob-mxhalf)/pinch_delta) #/(cosh((jglob-myhalf)/pinch_delta)*cosh((iglob-mxhalf)/pinch_delta))
                            velstripe = tanh((iglob-mxhalf)/pinch_delta)



                            if conf.trigger:
                                pinch_corr = (1./(cosh((jglob-myhalf)/pinch_delta) \
                                                 *cosh((iglob-mxhalf)/delta)*triggerz))

                                yee.by[l,m,n] = binit*stripetanh
                                yee.bz[l,m,n] = binit*stripetanh*(1.0 - pinch_corr)

                                yee.ey[l,m,n] = (-beta)*velstripe*yee.bz[l,m,n] 

                                #drive to trigger reconnection in the middle of the box; 
                                #the coefficient should be the desired ExB speed
                                yee.ez[l,m,n] = (+beta)*velstripe*yee.by[l,m,n] #+ conf.trigger_field*abs(yee.by[l,m,n])*pinch_corr

                            else:
                                yee.by[l,m,n] = binit*stripetanh 
                                yee.bz[l,m,n] = binit*np.sqrt(conf.sigma_ext) #add guide field

                                yee.ey[l,m,n] = (-beta)*velstripe*yee.bz[l,m,n] 
                                yee.ez[l,m,n] = (+beta)*velstripe*yee.by[l,m,n]

                            yee.ex[l,m,n] = 0.0


                            #hot current sheet
                            #beta_drift = sqrt(sigma)
                            beta_drift = 0.5
                            if not(conf.periodicx):
                                num_plasma = 1.0/(cosh((iglob-mxhalf)/delta))**2.
                            else:
                                #num_plasma = 1.0/(cosh(dstripe*lstripe*sin(2.*pi*(iglob-mxhalf)/lstripe)))**2.*stripecosh
                                num_plasma = 1.0/cosh(Lx*sin(2.*pi*(iglob - mxhalf)/Lx)/delta/2.0/pi)**2.

                            gamma_drift = sqrt(1./(1.-beta_drift**2.))
                            if conf.periodicx:
                                gamma_drift = gamma_drift * np.sign(cos(2.*pi*(iglob-mxhalf)/Lx))
                                beta_drift = sqrt(1.-1./gamma_drift**2) * np.sign(gamma_drift)

                            yee.ez[l,m,n] += beta_drift*num_plasma*binit



                # copy values to boundary cells
                try:
                    for n in range(conf.NzMesh):
                        for m in range(conf.NyMesh):
                            for l in range(conf.NxMesh):
                                c.ex_ref[l,m,n] = yee.ex[l,m,n]
                                c.ey_ref[l,m,n] = yee.ey[l,m,n]
                                c.ez_ref[l,m,n] = yee.ez[l,m,n]

                                c.bx_ref[l,m,n] = yee.bx[l,m,n]
                                c.by_ref[l,m,n] = yee.by[l,m,n]
                                c.bz_ref[l,m,n] = yee.bz[l,m,n]
                except:
                    #print("cell ({},{}) is not boundary cell".format(ii,jj))
                    pass


#all tile generator
def tiles_all(grid):
    for cid in grid.get_tile_ids():
        tile = grid.get_tile(cid)
        yield tile

#local tile generator
def tiles_local(grid):
    for cid in grid.get_local_tiles():
        tile = grid.get_tile(cid)
        yield tile



if __name__ == "__main__":

    np.random.seed(42)

    do_plots = True
    do_print = False
    if MPI.COMM_WORLD.Get_rank() == 0:
        do_print =True

    ################################################## 
    # set up plotting and figure
    try:
        if do_plots:
            plt.fig = plt.figure(1, figsize=(8,10))
            plt.rc('font', family='serif', size=12)
            plt.rc('xtick')
            plt.rc('ytick')
            
            gs = plt.GridSpec(4, 3)
            gs.update(hspace = 0.5)
            
            axs = []
            for ai in range(12):
                axs.append( plt.subplot(gs[ai]) )
    except:
        #print()
        pass


    # Timer for profiling
    timer = Timer()
    timer.start("total")
    timer.start("init")
    timer.do_print = do_print


    # parse command line arguments
    parser = argparse.ArgumentParser(description='Force-Free MHD simulation driver')
    parser.add_argument('--conf', dest='conf_filename', default=None,
                       help='Name of the configuration file (default: None)')
    args = parser.parse_args()
    if args.conf_filename == None:
        conf = Configuration('config-test.ini', do_print=do_print) 
    else:
        if do_print:
            print("Reading configuration setup from ", args.conf_filename)
        conf = Configuration(args.conf_filename, do_print=do_print)

    grid = corgi.Grid(conf.Nx, conf.Ny, conf.Nz)

    xmin = 0.0
    xmax = conf.Nx*conf.NxMesh
    ymin = 0.0
    ymax = conf.Ny*conf.NyMesh

    grid.set_grid_lims(xmin, xmax, ymin, ymax)
    init.loadMpi2D(grid)

    loadTiles(grid, conf)

    ################################################## 
    # Path to be created 
    if grid.master():
        if not os.path.exists( conf.outdir ):
            os.makedirs(conf.outdir)
        if not os.path.exists( conf.outdir+"/restart" ):
            os.makedirs(conf.outdir+"/restart")
        if not os.path.exists( conf.outdir+"/full_output" ):
            os.makedirs(conf.outdir+"/full_output")


    do_initialization = True

    #check if this is the first time and we do not have any restart files
    if not os.path.exists( conf.outdir+'/restart/laps.txt'):
        conf.laprestart = -1 #to avoid next if statement

    # restart from latest file
    deep_io_switch = 0
    if conf.laprestart >= 0:
        do_initialization = False

        #switch between automatic restart and user-defined lap
        if conf.laprestart == 0:
            #get latest restart file from housekeeping file
            with open(conf.outdir+"/restart/laps.txt", "r") as lapfile:
                #lapfile.write("{},{}\n".format(lap, deep_io_switch))
                lines = lapfile.readlines()
                slap, sdeep_io_switch = lines[-1].strip().split(',')
                lap = int(slap)
                deep_io_switch = int(sdeep_io_switch)

            read_lap = deep_io_switch
            odir = conf.outdir + '/restart'

        elif conf.laprestart > 0:
            lap = conf.laprestart
            read_lap = lap
            odir = conf.outdir + '/full_output'

        if do_print:
            print("...reading Yee lattices (lap {}) from {}".format(read_lap, odir))
        pyvlv.read_yee(grid, read_lap, odir)

        lap += 1 #step one step ahead


    # initialize
    if do_initialization:
        lap = 0
        np.random.seed(1)
        #insert_em(grid, conf)
        #insert_em_harris_sheet(grid, conf)
        insert_guide_field(grid, conf)

    #static load balancing setup; communicate neighbor info once
    grid.analyze_boundaries()
    grid.send_tiles()
    grid.recv_tiles()
    initialize_virtuals(grid, conf)

    timer.stop("init") 
    timer.stats("init") 


    # end of initialization
    ################################################## 

    # visualize initial condition
    if do_plots:
        plconf = dict(curval = 0.05, elval=0.2, bfval = 0.4)
        try:
            #plotNode( axs[0], grid, conf)
            yee = getYee2D(grid, conf)
            plot2dYee(axs[0],  yee, grid, conf, 'jx1', vmin=-plconf['curval'], vmax=plconf['curval'])
            plot2dYee(axs[1],  yee, grid, conf, 'jy1', vmin=-plconf['curval'], vmax=plconf['curval'])
            plot2dYee(axs[2],  yee, grid, conf, 'jz1', vmin=-plconf['curval'], vmax=plconf['curval'])

            plot2dYee(axs[3],  yee, grid, conf, 'jx' , vmin=-plconf['curval'], vmax=plconf['curval'])
            plot2dYee(axs[4],  yee, grid, conf, 'jy' , vmin=-plconf['curval'], vmax=plconf['curval'])
            plot2dYee(axs[5],  yee, grid, conf, 'jz' , vmin=-plconf['curval'], vmax=plconf['curval'])

            plot2dYee(axs[6],  yee, grid, conf, 'ex' , vmin=-plconf['elval'], vmax=plconf['elval'])
            plot2dYee(axs[7],  yee, grid, conf, 'ey' , vmin=-plconf['elval'], vmax=plconf['elval'])
            plot2dYee(axs[8],  yee, grid, conf, 'ez' , vmin=-plconf['elval'], vmax=plconf['elval'])

            plot2dYee(axs[9],  yee, grid, conf, 'bx' , vmin=-plconf['bfval'], vmax=plconf['bfval'])
            plot2dYee(axs[10], yee, grid, conf, 'by' , vmin=-plconf['bfval'], vmax=plconf['bfval'])
            plot2dYee(axs[11], yee, grid, conf, 'bz' , vmin=-plconf['bfval'], vmax=plconf['bfval'])
            saveVisz(lap, grid, conf)
            saveVisz(-1, grid, conf)
        except:

            pass

    fldprop  = pyfld.FDTD2()
    driftcur = pyffe.DriftCurrent(conf.NxMesh, conf.NyMesh, conf.NzMesh)

    # quick field snapshots
    qwriter  = pyfld.QuickWriter(conf.outdir, 
            conf.Nx, conf.NxMesh,
            conf.Ny, conf.NyMesh,
            conf.Nz, conf.NzMesh,
            conf.stride)

    ################################################## 
    # Langeving antenna
    if do_initialization:

        # direct B_{x,y} perturbation
        if True:
            conf.min_mode = 1
            conf.max_mode = 4
            conf.drive_ampl = 1.
            antenna = Antenna(conf.min_mode, conf.max_mode, conf)
            for tile in tiles_local(grid): 
                antenna.add_driving(tile)


    # update initial boundaries
    grid.send_data(1) 
    grid.recv_data(1) 
    grid.wait_data(1) 

    grid.send_data(2) 
    grid.recv_data(2) 
    grid.wait_data(2) 

    for tile in tiles_all(grid): 
        tile.update_boundaries(grid)



    ################################################## 
    sys.stdout.flush()

    #simulation loop
    time = lap*(conf.cfl/conf.c_omp)
    for lap in range(lap, conf.Nt+1):

        #FFE algorithm is:
        # Derivative
        # compute drift current
        # enforce E <= B 
        # subtract E_par

        #RK4 scheme is
        # k1 = dt * f(t         , y)
        # k2 = dt * f(t + 0.5*dt, y + 0.5*k1)
        # k3 = dt * f(t + 0.5*dt, y + 0.5*k2)
        # k4 = dt * f(t + dt    , y + k3)
        # vy[i] = y = y + (k1 + k2 + k2 + k3 + k3 + k4) / 6

        #Coefficients correspond to (dt, dy, y_i)
        #for (dti, dyi, yi) in [
        #        (0.0, 0.0, 0),
        #        (0.5, 0.5, 1),
        #        (0.5, 0.5, 2),
        #        (1.0, 1.0, 3)]:

        # Euler stepping
        for (rk_alpha, rk_beta, rk_i) in [ (1.0, 0.0, 0), ]:


            ################################################## 
            # Initialize Runge-Kutta variables
            t1 = timer.start_comp("RK_init")

            dt = 0.0 + rk_alpha
            for tile in tiles_local(grid): 
                yee  = tile.get_yee(0)    #get current working storage
                
                if rk_i == 0:
                    #store y_n step to Y_0 at the beginning of the lap
                    yee_0 = tile.get_step(rk_i) #get reference to rk_i:th RK sub-step storage
                    yee_0.set_yee(yee)
                else:
                    # set initial starting point according to RK scheme
                    #
                    # RK formula applied is y = y0 + rk_beta*ys[rk_i]
                    yee_m1 = tile.get_step(rk_i-1) 
                    set_step(yee, yee_0 + rk_beta*yee_m1)


            timer.stop_comp(t1)


            ################################################## 
            #push B half
            t1 = timer.start_comp("push_half_b0")
            for tile in tiles_all(grid): 
                fldprop.push_half_b(tile)
            timer.stop_comp(t1)


            ################################################## 
            # compute drift current

            #empty current arrays
            for tile in tiles_all(grid): 
                tile.clear_current()

            #update boundaries
            t1 = timer.start_comp("upd_bc0")
            for tile in tiles_all(grid): 
                tile.update_boundaries(grid)
            timer.stop_comp(t1)


            t1 = timer.start_comp("compute_current")
            for tile in tiles_all(grid): 
                driftcur.comp_drift_cur(tile)
            timer.stop_comp(t1)


            ################################################## 
            # compute parallel current

            #update boundaries
            t1 = timer.start_comp("upd_bc1")
            for tile in tiles_all(grid): 
                tile.update_boundaries(grid)
            timer.stop_comp(t1)

            #parallel current
            t1 = timer.start_comp("compute_para_current")
            for tile in tiles_all(grid): 
                driftcur.comp_parallel_cur(tile)
            timer.stop_comp(t1)


            ################################################## 
            # limiter (local)

            #update boundaries
            t1 = timer.start_comp("upd_bc2")
            for tile in tiles_local(grid): 
                tile.update_boundaries(grid)
            timer.stop_comp(t1)

            #apply limiter
            t1 = timer.start_comp("limiter")
            for tile in tiles_local(grid): 
                driftcur.limiter(tile)
            timer.stop_comp(t1)


            ################################################## 
            # push half B (local)

            # comm E
            t1 = timer.start_comp("mpi_e0")
            grid.send_data(1) 
            grid.recv_data(1) 
            grid.wait_data(1) 
            timer.stop_comp(t1)

            #update boundaries
            t1 = timer.start_comp("upd_bc3")
            for tile in tiles_local(grid): 
                tile.update_boundaries(grid)
            timer.stop_comp(t1)

            #push B half
            t1 = timer.start_comp("push_half_b0")
            for tile in tiles_local(grid): 
                fldprop.push_half_b(tile)
            timer.stop_comp(t1)


            ################################################## 
            # push E (all)

            # comm B
            t1 = timer.start_comp("mpi_b1")
            grid.send_data(2) 
            grid.recv_data(2) 
            grid.wait_data(2) 
            timer.stop_comp(t1)

            #update boundaries
            t1 = timer.start_comp("upd_bc4")
            for tile in tiles_all(grid): 
                tile.update_boundaries(grid)
            timer.stop_comp(t1)

            #push B half
            t1 = timer.start_comp("push_e")
            for tile in tiles_all(grid): 
                fldprop.push_e(tile)
            timer.stop_comp(t1)

            #update boundaries
            t1 = timer.start_comp("upd_bc5")
            for tile in tiles_all(grid): 
                tile.update_boundaries(grid)
            timer.stop_comp(t1)


            #FIXME: check that it is not a copy
            #for tile in tiles_local(grid): 
            #    ystep = tile.get_step(rk_i) #get reference to rk_i:th RK sub-step storage
            #    yee = tile.get_yee(0)
            #    for j in range(conf.NyMesh):
            #        for i in range(conf.NxMesh):
            #            if yee.ex[i,j,0] == ystep.ex[i,j,0]:
            #                print("warning at {},{}: n+1 {} vs n {}".format(i,j,yee.ex[i,j,0], ystep.ex[i,j,0]))

            # save current RK substep 
            for tile in tiles_local(grid): 
                yee_i = tile.get_step(rk_i) #get reference to rk_i:th RK sub-step storage
                yee_i.set_yee(yee)


        # RK reduction step
        t1 = timer.start_comp("RK_sum")
        for tile in tiles_local(grid): 
            ynp1 = tile.get_yee() #get reference to working storage

            #get reference to rk_i:th RK sub-step storage
            y0 = tile.get_step(0) 
            y1 = tile.get_step(1) 
            y2 = tile.get_step(2)
            y3 = tile.get_step(3)

            #RK4 summation
            y0 *= 1.0/6.0
            y1 *= 2.0/6.0
            y2 *= 2.0/6.0
            y2 *= 1.0/6.0

            set_step(ynp1, (y0 + y1 + y2 + y3) )

        timer.stop_comp(t1)


        ##################################################
        # data reduction and I/O

        timer.lap("step")
        if (lap % conf.interval == 0):
            if do_print:
                print("--------------------------------------------------")
                print("------ lap: {} / t: {}".format(lap, time)) 

            timer.stats("step")
            timer.comp_stats()
            timer.purge_comps()
            
            #analyze (independent)
            timer.start("io")


            #shallow IO
            qwriter.write(grid, lap) #quick field snapshots

            #deep IO
            if (conf.full_interval != -1 and (lap % conf.full_interval == 0) and (lap > 0)):
                pyvlv.write_yee(grid,      lap, conf.outdir + "/full_output/" )

            #restart IO (overwrites)
            if ((lap % conf.restart == 0) and (lap > 0)):
                #flip between two sets of files
                deep_io_switch = 1 if deep_io_switch == 0 else 0

                pyvlv.write_yee(grid,      deep_io_switch, conf.outdir + "/restart/" )

                #if successful adjust info file
                MPI.COMM_WORLD.barrier()
                if grid.rank() == 0:
                    with open(conf.outdir+"/restart/laps.txt", "a") as lapfile:
                        lapfile.write("{},{}\n".format(lap, deep_io_switch))

            #--------------------------------------------------
            #2D plots
            #try:
            if True:
                if do_plots:
                    #plotNode(axs[0], grid, conf)

                    yee = getYee2D(grid, conf)
                    plot2dYee(axs[0],  yee, grid, conf, 'jx1', vmin=-plconf['curval'], vmax=plconf['curval'])
                    plot2dYee(axs[1],  yee, grid, conf, 'jy1', vmin=-plconf['curval'], vmax=plconf['curval'])
                    plot2dYee(axs[2],  yee, grid, conf, 'jz1', vmin=-plconf['curval'], vmax=plconf['curval'])

                    plot2dYee(axs[3],  yee, grid, conf, 'jx' , vmin=-plconf['curval'], vmax=plconf['curval'])
                    plot2dYee(axs[4],  yee, grid, conf, 'jy' , vmin=-plconf['curval'], vmax=plconf['curval'])
                    plot2dYee(axs[5],  yee, grid, conf, 'jz' , vmin=-plconf['curval'], vmax=plconf['curval'])

                    plot2dYee(axs[6],  yee, grid, conf, 'ex' , vmin=-plconf['elval'], vmax=plconf['elval'])
                    plot2dYee(axs[7],  yee, grid, conf, 'ey' , vmin=-plconf['elval'], vmax=plconf['elval'])
                    plot2dYee(axs[8],  yee, grid, conf, 'ez' , vmin=-plconf['elval'], vmax=plconf['elval'])

                    plot2dYee(axs[9],  yee, grid, conf, 'bx' , vmin=-plconf['bfval'], vmax=plconf['bfval'])
                    plot2dYee(axs[10], yee, grid, conf, 'by' , vmin=-plconf['bfval'], vmax=plconf['bfval'])
                    plot2dYee(axs[11], yee, grid, conf, 'bz' , vmin=-plconf['bfval'], vmax=plconf['bfval'])
                    saveVisz(lap, grid, conf)

            #except:
            #    print()
            #    pass
            timer.stop("io")


            timer.stats("io")
            timer.start("step") #refresh lap counter (avoids IO profiling)

            sys.stdout.flush()

        #MPI.COMM_WORLD.barrier()
        #sleep(0.2)
        time += conf.cfl/conf.c_omp
    #end of loop


    timer.stop("total")
    timer.stats("total")

