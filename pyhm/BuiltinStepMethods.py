import numpy as np
import pdb
import Utils

"""
This module contains definitions for algorithms to be used by Sampler objects
to sample from the posterior distribution of models. Currently, it only contains
the definition for a basic Metropolis sampler. It would be nice to add in a
routine for doing nested sampling.
"""

class MetropolisHastings():
    """
    Metropolis-Hastings sampling algorithm with Gaussian proposal distributions
    for each of the free parameters.
    """

    def __init__( self, proposal_distribution=None, step_sizes=None ):
        """
        Initialises the sampling algorithm.
        """
        if proposal_distribution==None:
            self.proposal_distribution = Utils.gaussian_random_draw
        else:
            self.proposal_distribution = proposal_distribution

        if step_sizes==None:
            self.step_sizes = {}
        else:
            self.step_sizes = step_sizes

    def propose( self, unobs_stochs ):
        """
        Proposes a step in the parameter space.
        """
        keys = unobs_stochs
        for key in keys:
            unobs_stochs[key].value += self.proposal_distribution( mu=0.0, sigma=self.step_sizes[key] )

    def decide( self, current_logp, new_logp ):
        """
        Decides whether or not to accept the current step.
        """
        beta = new_logp - current_logp
        if beta>0:
            decision = True
        else: 
            alpha = np.exp( beta )
            z = np.random.random()
            if z<=alpha:
                decision = True
            else:
                decision = False
        return decision

    def pre_tune( self, mcmc, ntune_iterlim=0, tune_interval=None, verbose=False ):
        """
        Adjusts step sizes to give a step acceptance rate of 20-35%.
        """
        print '\nTuning step sizes...'
        m = ntune_iterlim
        n = tune_interval
        unobs_stochs = mcmc.model.free
        keys = unobs_stochs.keys()
        step_sizes = self.step_sizes
        if self.step_sizes==None:
            self.step_sizes = {}
            for key in keys:
                self.step_sizes[key] = 1.
        npars = len( keys )

        # Make a record of the starting values for each parameter:
        orig_stoch_values = {}
        for key in keys:
            orig_stoch_values[key] = unobs_stochs[key].value

        # First of all, we will tune the relative step sizes for
        # all of the parameters by taking steps one parameter at
        # a time. Initialise the arrays that will record the results:
        tuning_chains = {}
        for key in keys:
            tuning_chains[key] = {}
        current_values = {}
        for key in keys:
            tuning_chains[key]['values'] = np.zeros( n, dtype=unobs_stochs[key].dtype )
            tuning_chains[key]['logp'] = np.zeros( n, dtype=float )
            tuning_chains[key]['accepted'] = np.zeros( n, dtype=int )
            current_values[key] = unobs_stochs[key].value

        # Define variables that track the total number of tuning
        # steps that have been taken and the consecutive number of
        # successful tune_intervals:
        nconsecutive = 5
        for j in range( npars ):

            i = 0 # iteration counter
            nsuccess = 0 # number of consecutive successes
            key_j = keys[j]

            # Proceed to perturb the current parameter only, carrying
            # on until the iteration limit has been reached:
            accfrac_j = 0
            while i<m+1:

                step_size_j = self.step_sizes[key_j]

                # If there have been nconsecutive successful tune intervals
                # in a row, break the loop:
                if nsuccess>=nconsecutive:
                    self.step_sizes[key_j] *= 0.3
                    break

                # If the iteration limit has been reached, return an error:
                elif i==m:
                    err_str = 'Aborting tuning - exceeded {0} steps'.format( m )
                    err_str += '\n...consider reducing tune_interval'
                    raise StandardError( err_str )

                # Otherwise, proceed with the tuning:
                else:
                    k = i%n # iteration number within current tuning interval
                    i += 1
                    current_logp = mcmc.logp()

                    # If this is the first iteration in a new tuning interval,
                    # reset all parameters to their original values to avoid
                    # drifting into low likelihood regions of parameter space:
                    if k==0:
                        for key in keys:
                            unobs_stochs[key].value = orig_stoch_values[key]

                    # Take a step in the current parameter while holding the 
                    # rest fixed:
                    step_size_j = self.step_sizes[key_j]
                    unobs_stochs[key_j].value += self.proposal_distribution( mu=0.0, sigma=step_size_j )

                    # Decide if the step is to be accepted:
                    new_logp = mcmc.logp()
                    tuning_chains[key_j]['accepted'][k] = self.decide( current_logp, new_logp )

                    # Update the value of the associated stochastic object:
                    if ( tuning_chains[key_j]['accepted'][k]==True ):
                        current_logp = new_logp
                        current_values[key_j] = unobs_stochs[key_j].value
                    else:
                        unobs_stochs[key_j].value = current_values[key_j]

                    # Add the result to the chain:
                    tuning_chains[key_j]['values'][k] = current_values[key_j]
                    tuning_chains[key_j]['logp'][k] = mcmc.model.logp()
                    
                    # If we have reached the end of the current tuning interval,
                    # adjust the step size of the current parameter based on the
                    # fraction of steps that were accepted:
                    if k==n-1:
                        naccepted_j  = np.sum( tuning_chains[key_j]['accepted'] )
                        accfrac_j = naccepted_j/float( n )
                        if ( accfrac_j<=0.01 ):
                            self.step_sizes[key_j] /= 5.0
                        elif ( accfrac_j>0.01 )*( accfrac_j<=0.05 ):
                            self.step_sizes[key_j] /= 2.0
                        elif ( accfrac_j>0.05 )*( accfrac_j<=0.10 ):
                            self.step_sizes[key_j] /= 1.5
                        elif ( accfrac_j>0.10 )*( accfrac_j<=0.15 ):
                            self.step_sizes[key_j] /= 1.2
                        elif ( accfrac_j>0.15 )*( accfrac_j<0.2 ):
                            self.step_sizes[key_j] /= 1.1
                        elif ( accfrac_j>0.20 )*( accfrac_j<0.25 ):
                            self.step_sizes[key_j] /= 1.01
                        elif ( accfrac_j>0.35 )*( accfrac_j<=0.40 ):
                            self.step_sizes[key_j] *= 1.01
                        elif ( accfrac_j>0.40 )*( accfrac_j<=0.45 ):
                            self.step_sizes[key_j] *= 1.1
                        elif ( accfrac_j>0.45 )*( accfrac_j<=0.50 ):
                            self.step_sizes[key_j] *= 1.2
                        elif ( accfrac_j>0.50 )*( accfrac_j<=0.55 ):
                            self.step_sizes[key_j] *= 1.5
                        elif ( accfrac_j>0.55 )*( accfrac_j<=0.60 ):
                            self.step_sizes[key_j] *= 2.0
                        elif ( accfrac_j>0.60 ):
                            self.step_sizes[key_j] *= 5.0

                # If the end of a tune interval has been reached, check
                # if all the acceptance rates were in the required range:
                if ( k==n-1 ):
                    if ( accfrac_j>=0.2 )*( accfrac_j<=0.40 ):
                        nsuccess += 1
                    else:
                        nsuccess = 0
                    if verbose==True:
                        print '\nPre-tuning update for parameter {0} ({1} of {2}):'\
                              .format( key_j, j+1, npars )
                        print 'Consecutive successes = {0}'.format( nsuccess )
                        print 'Accepted fraction from last {0} steps = {1}'\
                              .format( n, accfrac_j )
                        print '(require {0} consecutive intervals with acceptance rate 0.2-0.4)'\
                              .format( nconsecutive )
                        print 'Median value of last {0} steps: median( {1} )={2} '\
                              .format( n, key_j, np.median( current_values[key_j] ) )
                        print 'Starting value for comparison: {0}'.format( orig_stoch_values[key_j] )

        # Having tuned the relative step sizes, we must now rescale them
        # together to refine the joint step sizes:
        i = 0
        nsuccess = 0
        rescale_factor = 1.0/np.sqrt( npars )
        tuning_chain = np.zeros( n, dtype=int )
        current_logp = mcmc.logp()
        if verbose==True:
            print '\n\nNow tuning the step sizes simultaneously...\n'
        while i<m+1:

            # If there have been nconsecutive successful tune intervals
            # in a row, break the loop:
            if nsuccess>=nconsecutive:
                break

            # If the iteration limit has been reached, return an error:
            elif i==m:
                err_str = 'Aborting tuning - exceeded {0} steps'.format( m )
                err_str += '\n...consider reducing tune_interval'
                raise StandardError( err_str )

            # Otherwise, proceed with the tuning:
            else:
                k = i%n # iteration number within current tuning interval
                i += 1
                
                # If this is the first iteration in a new tuning interval,
                # reset all parameters to their original values to avoid
                # drifting into low likelihood regions of parameter space:
                if k==0:
                    for key in keys:
                        unobs_stochs[key].value = orig_stoch_values[key]
                    
                # Take a step in all of the parameters simultaneously:
                for key in keys:

                    # If this is the first iteration in a new tuning interval,
                    # rescale the step sizes by a constant factor before
                    # taking the step:
                    if k==0:
                        self.step_sizes[key] *= rescale_factor
                    unobs_stochs[key].value += self.proposal_distribution( mu=0.0, sigma=self.step_sizes[key] )

                # Decide if the step is to be accepted:
                new_logp = mcmc.logp()
                tuning_chain[k] = self.decide( current_logp, new_logp )
                if ( tuning_chain[k]==True ):
                    current_logp = new_logp
                    for key in keys:
                        current_values[key] = unobs_stochs[key].value
                else:
                    for key in keys:
                        unobs_stochs[key].value = current_values[key]

                # If we have reached the end of the current tuning interval,
                # adjust the step size rescaling factor based on the fraction
                # of steps that were accepted:
                if k==n-1:
                    naccepted = np.sum( tuning_chain )
                    accfrac = naccepted/float( n )
                    if ( accfrac>=0.2 )*( accfrac<=0.35 ):
                        nsuccess += 1
                        rescale_factor = 1.0
                    else:
                        nsuccess = 0
                        if ( accfrac<=0.01 ):
                            rescale_factor = 1./2.0
                        elif ( accfrac>0.01 )*( accfrac<=0.05 ):
                            rescale_factor = 1./1.5
                        elif ( accfrac>0.05 )*( accfrac<=0.10 ):
                            rescale_factor = 1./1.2
                        elif ( accfrac>0.10 )*( accfrac<=0.15 ):
                            rescale_factor = 1./1.1
                        elif ( accfrac>0.15 )*( accfrac<0.2 ):
                            rescale_factor = 1./1.01
                        elif ( accfrac>0.35 )*( accfrac<=0.45 ):
                            rescale_factor = 1.01
                        elif ( accfrac>0.45 )*( accfrac<=0.50 ):
                            rescale_factor = 1.1
                        elif ( accfrac>0.50 )*( accfrac<=0.55 ):
                            rescale_factor = 1.2
                        elif ( accfrac>0.55 )*( accfrac<=0.60 ):
                            rescale_factor = 1.5
                        elif ( accfrac>0.60 ):
                            rescale_factor = 2.

                    if verbose==True:
                        print 'Consecutive successes = {0}'.format( nsuccess )
                        print 'Accepted fraction from last {0} steps = {1}'\
                              .format( n, accfrac )

        print 'Finished tuning with acceptance rate of {0:.1f}%'.format( accfrac*100 )

        return None
