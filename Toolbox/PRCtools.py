"""Toolbox for phase response curves measured by finite perturbations
"""

import numpy as np
from PyDSTool import Pointset, Model, embed
from PyDSTool.Trajectory import pointset_to_traj

#from pylab import figure, plot

#__all__ = []

# -------------------------------------------------

def one_period_traj(model, ev_name, ev_t_tol, ev_norm_tol, T_est,
                    verbose=False, initial_settle=6, restore_old_ics=False,
                    use_quadratic_interp=False):
    """
    Utility to extract a single period of a limit cycle of the model using forward
    integration, up to a tolerance given in terms of both the period and the norm of the
    vector of variables in the limit cycle at the period endpoints.

    Requires a non-terminal event in the model that is detected exactly once per period.
    Assumes model initial conditions are already in domain of attraction for limit cycle.

    T_est is an initial estimate of period.
    use_quadratic_interp option (default False) indicates whether to make the returned
    trajectory interpolated more accurately using quadratic functions rather than linear ones.
    This option takes a lot longer to complete!

    The model argument can be an instance of a Generator class or Model class.

    Returned trajectory will have name 'one_period'.
    """
    if not isinstance(model, Model.Model):
        # temporarily embed into a model object
        model = embed(model)
    if use_quadratic_interp:
        old_interp_setting = model.query('algparams')['poly_interp']
        model.set(algparams={'poly_interp': True})
    trajname = '_test_period_'
    old_ics = model.query('ics')
    settle = initial_settle
    tries = 1
    success = False
    while not success and tries < 8:
        model.compute(trajname=trajname, tdata=[0,T_est*(settle+0.2)], force=True)
        evts = model.getTrajEventTimes(trajname, ev_name)
        all_evs = model.getTrajEventTimes(trajname)
        if len(evts) <= 2:
            raise RuntimeError("Not enough events found")
        ref_ic = model(trajname, evts[-1])
        t_check = 10000*np.ones((tries,),float)
        norm_check = 10000*np.ones((tries,),float)
        T = np.zeros((tries,),float)
        look_range = range(1, min((tries+1, len(evts))))
        if verbose:
            print "\n Tries: ", tries, "\n"
        for lookback in look_range:
            try:
                d_evts = [evts[i]-evts[i-lookback] for i in \
                                    range(lookback, len(evts))]
            except KeyError:
                # no more events left to look back at
                break
            else:
                prev_val = model(trajname, evts[-(1+lookback)])
                t_check[lookback-1] = abs(d_evts[-1]-d_evts[-2])
                norm_check[lookback-1] = np.linalg.norm(ref_ic-prev_val)
                T[lookback-1] = d_evts[-1]
        T_est = T[0]
        t_ix = np.argmin(t_check)
        n_ix = np.argmin(norm_check)
        ix1 = min((t_ix, n_ix))
        ix2 = max((t_ix, n_ix))
        if verbose:
            print t_check, norm_check, T
            print ix1, ix2
        if t_check[ix1] < ev_t_tol and norm_check[ix1] < ev_norm_tol:
            success = True
            T_final = T[ix1]
        elif ix1 != ix2 and t_check[ix2] < ev_t_tol and norm_check[ix2] < ev_norm_tol:
            success = True
            T_final = T[ix2]
        else:
            tries += 1
            settle = tries*2
            model.set(ics = ref_ic)
    if success:
        model.set(ics=ref_ic, tdata=[0, T_final])
        model.compute(trajname='one_period', force=True)
        ref_traj = model['one_period']
        # insert the ON event at beginning of traj
        ref_traj.events[ev_name] = Pointset(indepvararray=[0],
                                        coordarray=np.array([ref_ic.coordarray]).T,
                                        coordnames=ref_ic.coordnames)
        ref_pts = ref_traj.sample()
        # restore old ICs
        if restore_old_ics:
            model.set(ics=old_ics)
        if use_quadratic_interp:
            model.set(algparams={'poly_interp': old_interp_setting})
        return ref_traj, ref_pts, T_final
    else:
        raise RuntimeError("Failure to converge after 80 iterations")


def _default_pert(model, ic, pertcoord, pertsize):
    ic[pertcoord] += pertsize
    return ic


def finitePRC(model, ref_traj_period, evname, pertcoord, pertsize=0.05,
              settle=5, verbose=False, skip=1, do_pert=_default_pert, keep_trajs=False):
    """Pass a Generator or Model instance for model.
    Pass a Trajectory or Pointset for the ref_traj_period argument.
    Pass the event name in the model that indicates the periodicity.
    Use skip > 1 to sub-sample the points computed along the trajectory at
     the skip rate.
    Use a do_pert function to do any non-standard perturbation, e.g. if there
     are domain boundary conditions that need special treatment. This function
     takes four arguments (model, ic, pertcoord, pertsize) and returns the new
     point ic (not just ic[pertcoord]).

    Note: Depending on your model, there may be regions of the PRC that are
    offset by a constant amount to the rest of the PRC. This is a "wart" that
    needs improvement.
    """
    if not isinstance(model, Model.Model):
        # temporarily embed into a model object
        model = embed(model)
    try:
        all_pts = ref_traj_period.sample()
        ref_pts = all_pts[::skip]
        if ref_pts[-1] != all_pts[-1]:
            # ensure last point at t=T is present
            ref_pts.append(all_pts[[-1]])
        T = ref_traj_period.indepdomain[1]-ref_traj_period.indepdomain[0]
    except AttributeError:
        # already passed points
        ref_pts = ref_traj_period[::skip]
        if ref_pts[-1] != ref_traj_period[-1]:
            ref_pts.append(ref_traj_period[[-1]])
        T = ref_traj_period.indepvararray[-1]-ref_traj_period.indepvararray[0]
    ref_ts = ref_pts.indepvararray
    PRCvals = []
    t_off = 0
    if verbose:
        print "Period T =", T
    for i, t0 in enumerate(ref_ts):
        ic = ref_pts[i]
        ic = do_pert(model, ic, pertcoord, pertsize)
        if verbose:
            print i, "of", len(ref_ts), ": t0 = ", t0, "of", T, "  t_end", settle*T+t0
            print "   ", ic
        model.set(ics=ic, tdata=[0,settle*T+t0])
        if keep_trajs:
            model.compute(trajname='pert_%i'%i, force=True)
            evts = model.getTrajEventTimes('pert_%i'%i, evname)
        else:
            model.compute(trajname='pert', force=True)
            evts = model.getTrajEventTimes('pert', evname)
        if verbose:
            print "    Last event:", evts[-1]
        val = -np.mod(evts[-1]+t0, T)/T
        if abs(val) > 0.5:
            val = val+1
        PRCvals.append(val)
    return Pointset(coordarray=[PRCvals], coordnames=['D_phase'], indepvararray=ref_ts, indepvarname='t')


def fix_PRC(PRC, tol=0.01):
    new_vals = []
    for ix, phase in enumerate(PRC['D_phase']):
        if phase > 0.5-tol:
            phase = phase - 0.5
        elif phase < tol-0.5:
            phase = phase + 0.5
        else:
            continue
        # drop through
        new_vals.append( (ix, phase) )
    for ix, phase in new_vals:
        PRC.coordarray[0][ix] = phase
    return PRC