import numpy as np
import cPickle
import pdb, sys, time
try:
    from ProgressBar import progressbar
    progressbar_imported = True
except:
    print '\nProblem importing ProgressBar - skipping'
    print '(perhaps ipython not installed?)\n'
    progressbar_imported = False

"""
This module contains various utility routines, including the
backends for generating samples from a Model and taking random
draws from a Model.
"""

def sample( sampler, nsteps=1000, ntune_iterlim=None, tune_interval=None, show_progressbar=True, verbose=False ):
    """
    Generate samples from the model posterior distribution.
    """
    
    # Check that a StepMethod has been assigned:
    if sampler.step_method==None:
        err_str = 'Step method must be assigned before sampling can begin'
        raise StandardError( err_str )
    else:
        step_method = sampler.step_method

    sampler.nsteps = nsteps

    # Initialise the chain:
    sampler.chain = {}
    sampler.chain['logp'] = np.zeros( nsteps, dtype=float )
    sampler.chain['accepted'] = np.zeros( nsteps, dtype=int )
    unobs_stochs = sampler.model.free
    unobs_stochs_keys = unobs_stochs.keys()
    for key in unobs_stochs_keys:
        dtype = unobs_stochs[key].dtype
        sampler.chain[key] = np.zeros( nsteps, dtype=dtype )

    # Install the current unobserved stochastic values
    # as the first step in the chain:
    current_values = {}
    for key in unobs_stochs_keys:
        current_values[key] = unobs_stochs[key].value
    current_logp = sampler.logp()
    
    # Determine if there will be tuning:
    if ( ntune_iterlim!=None )*( tune_interval!=None ):
        if hasattr( step_method, 'pre_tune' )==False:
            err_str = '\nStepMethod must have pre_tune() method assigned'
            raise ValueError( err_str )
        elif tune_interval==None:
            err_str = 'tune_interval must be set explicitly for pre-tuning'
            raise ValueError( err_str )
        else:
            step_method.pre_tune( sampler, ntune_iterlim=ntune_iterlim, \
                                  tune_interval=tune_interval, verbose=verbose )
    else:
        sampler.ntune_iterlim = None
        sampler.tune_interval = None

    # Proceed with the sampling:
    if ( sampler.show_progressbar==True )*\
       ( progressbar_imported==True ):
        pbar = progressbar( nsteps )
    for i in range( nsteps ):
        if ( sampler.show_progressbar==True )*( ( i+1 )%100==0 )*\
           ( progressbar_imported==True ):
            pbar.animate( i+1 )
        step_method.propose( unobs_stochs )
        new_logp = sampler.logp()
        sampler.chain['accepted'][i] = step_method.decide( current_logp, new_logp )
        if sampler.chain['accepted'][i]==True:
            current_logp = new_logp
            for key in unobs_stochs_keys:
                current_values[key] = unobs_stochs[key].value
        else:
            for key in unobs_stochs_keys:
                unobs_stochs[key].value = current_values[key]
        for key in unobs_stochs_keys:
            sampler.chain[key][i] = unobs_stochs[key].value
        sampler.chain['logp'][i] = current_logp
    if ( sampler.show_progressbar==True )*\
       ( progressbar_imported==True ):
        pbar.animate( nsteps )
        
    return None


def random_draw_from_Model( model ):
    """
    Takes a random draw from the Model prior. Care is
    taken to sample from the highest level of the model
    heirarchy first, and then propagate through.
    """
    
    unobs_stochs = model.free
    keys = unobs_stochs.keys()
    ancestries = []
    for key in keys:
        ancestries += [ model._ancestries[key] ]
    keys = np.array( keys, dtype=str )
    ancestries = np.array( ancestries, dtype=int )
    ixs = np.argsort( ancestries )
    keys = keys[ixs]
    ancestries = ancestries[ixs]
    for key in keys:
        unobs_stochs[key].random()
        
    return None


def pickle_chain( sampler, pickle_chain=None, thin_before_pickling=1 ):
    """
    Pickles the chain of samples generated from the model
    posterior distribution.
    """
    
    if pickle_chain==None:
        pickle_chain = 'chain.pkl'

    if thin_before_pickling>1:
        ixs = ( np.arange( sampler.nsteps )%thin_before_pickling==0 )
    else:
        ixs = np.arange( sampler.nsteps )
    ochain = {}
    for key in sampler.chain.keys():
        ochain[key] = sampler.chain[key][ixs]

    opickle_file = open( pickle_chain, 'w' )
    cPickle.dump( ochain, opickle_file )
    opickle_file.close()
    print '\nPickled chain as:\n  {0}'.format( pickle_chain )

    return None


def load_chain( chain_filename ):
    """
    Uses cPickle to load a pickled chain.
    """
    
    ifile = open( chain_filename, 'r' )
    chain = cPickle.load( ifile )
    ifile.close()

    return chain


def update_attributes( object, dictionary ):
    """
    For each element in the dictionary, creates an identical attribute
    for the object, using the dictionary key as the attribute name.
    """
    
    for k in dictionary:
        if hasattr( object, k )==False:
            try:
                setattr( object, k, dictionary[k] )
            except:
                pass

    return None


def assign_step_method( mcmc, step_method, **kwargs ):
    """
    Assigns a step method to a Sampler object.
    """
    
    mcmc.step_method = step_method( **kwargs )
    if hasattr( mcmc.step_method, 'pre_tune' )==True:
        def mcmc_pretune( ntune_iterlim=0, tune_interval=None, **kwargs_pre_tune ):
            mcmc.step_method.pre_tune( mcmc, ntune_iterlim=ntune_iterlim, \
                                       tune_interval=tune_interval, **kwargs_pre_tune )
            return None
        mcmc.pre_tune = mcmc_pretune

    return None


def trace_ancestries( model ):
    """
    For each stochastic in the model, this routine determines the
    number of generations along each of its lineages there are before
    a non-stochastic (i.e. deterministic) variable is reached. The 
    maximum number of such generations across all lineages is installed
    as an attribute of the Model object called _ancestries. The ancestries
    are required to determine how perturbations in model parameters
    propagate through to other parameters. For instance, if parameter X
    is perturbed, then it will affect the probability distributions of
    parameters lower down in the model hierarchy. This must be accounted
    for when calculating the log likelihood of a Model's current state or
    taking a random draw.
    """

    ancestries = {}
    # Go through each unobserved Stochastic object
    # one at a time:
    unobs_stochs = model.free
    for stoch_key in unobs_stochs:
        stoch = unobs_stochs[stoch_key]
        # Initialise the flags that will be used to determine
        # whether or not we've hit the top level of the model
        # heirarchy:
        counter = 0
        reached_base = False
        current_parents = stoch.parents
        while reached_base==False:
            parent_keys = current_parents.keys()
            grandparents = {}
            stoch_checks = []
            # Cycle through each parent in the current level
            # and record if they are stochastics or not:
            for parent_key in parent_keys:
                parent = current_parents[parent_key]
                try:
                    parent_stoch = parent.is_stochastic
                except:
                    parent_stoch = False
                stoch_checks += [ parent_stoch ]
                # If the current parent being examined is an
                # unobserved stochastic, then add it to the
                # group of grandparents for the next level:
                if parent_stoch==True:
                    for grandparent_key in parent.parents.keys():
                        grandparents[grandparent_key] = parent.parents[grandparent_key]
                    
            counter += 1
            if max( stoch_checks )==False:
                reached_base = True
            else:
                current_parents = grandparents
        ancestries[stoch_key] = counter
    model._ancestries = ancestries
    
    return None
    

def observed_stochastics( stochastics ):
    """
    Takes a dictionary of Stochs and returns a new
    dictionary containing only the observed Stochs.
    """
    
    true_stochastics = identify_stochastics( stochastics )
    keys = true_stochastics.keys()
    observed_stochastics = {}
    for key in keys:
        stochastic = true_stochastics[key]
        if stochastic.observed==True:
            observed_stochastics[key] = stochastic
        else:
            continue

    return observed_stochastics


def unobserved_stochastics( stochastics ):
    """
    Takes a dictionary of Stochs and returns a new
    dictionary containing only the unobserved Stochs.
    """

    true_stochastics = identify_stochastics( stochastics )
    keys = true_stochastics.keys()
    unobserved_stochastics = {}
    for key in keys:
        stochastic = true_stochastics[key]
        if stochastic.observed==False:
            unobserved_stochastics[key] = stochastic
        else:
            continue

    return unobserved_stochastics


def identify_stochastics( dictionary ):
    """
    Takes a dictionary of arbitrary objects and returns a
    new dictionary containing only the Stochs.
    """

    keys = dictionary.keys()
    stochastics = {}
    for key in keys:
        item = dictionary[key]
        try:
            if item.is_stochastic==True:
                stochastics[key] = item
        except:
            continue
        
    return stochastics


def stochastics_values( dictionary ):
    """
    Returns a dictionary containing the current values of
    any Stochs contained in an input dictionary.
    """
    
    keys = dictionary.keys()
    values = {}
    for key in keys:
        var = dictionary[key]
        try:
            if var.is_stochastic==True:
                values[key] = var.value
        except:
            values[key] = var
            
    return values


def extract_stochastics_values( dictionary ):
    """
    Takes as input a dictionary of variables and converts any
    Stochs to numerical values, including those that are
    contained in lists. The output is a new dictionary containing
    these numerical values.
    """
    
    kwargs = {}
    for key in dictionary.keys():

        element = dictionary[key]
        
        # Allow for the possibility that a list of
        # stochastics has been provided as a parent:
        if type( element )==list:

            kwargs[key] = []
            for element in element:

                try:
                    if element.is_stochastic==True:
                        if np.size( element.value )==1:
                            kwargs[ key ] += [ float( element.value ) ]
                        else:
                            kwargs[ key ] += [ element.value ]
                    else:
                        kwargs[ key ] += [ element ]
                except:
                    kwargs[ key ] += [ element ]

        else:
            try:
                if element.is_stochastic==True:
                    if np.size( element.value )==1:
                        kwargs[key] = float( element.value )
                    else:
                        kwargs[key] = element.value
                else:
                    kwargs[key] = element
            except:
                kwargs[key] = element
                
    return kwargs


def check_model_stochastics_names( model ):
    """
    Checks that no two Stochastic variables share
    the same name in a given Model.
    """
    
    stochastics = model.stochastics
    nstoch = len( stochastics )
    names = []
    for key in stochastics.keys():
        names += [ stochastics[key].name ]
    names = np.array( names, dtype=str )
    unique_names = np.unique( names )
    if nstoch!=len( unique_names ):
        err_str = 'Model variables do not all have unique names'
        raise ValueError( err_str )

    return None
        

def combine_chains( chain_list, nburn=0, thin=1 ):
    """
    Combines multiple chains into a single chain.

    CALLING

      new_chain = pyhm.combine_chains( chain_list, nburn=1000, thin=5 )

    The above would take a list of chains, cut 1000 samples from the start
    of each and thin by a factor of 5 before combining into a single chain.
    This is done separately for each parameter in the chain.
    """
    
    m = len( chain_list )
    keys = chain_list[0].keys()
    combined = {}
    for key in keys:
        combined[key] = []
        for i in range( m ):
            chain = chain_list[i][key][nburn:]
            n = len( chain.flatten() )
            ixs = ( np.arange( n )%thin==0 )
            combined[key] += [ chain[ixs] ]
        combined[key] = np.concatenate( combined[key] )

    return combined
    

def blank_random():
    """
    If an unobserved Stoch is defined without a random()
    function, this filler function will be used. It simply prints
    a message to screen stating that a random function hasn't
    been defined.
    """
    
    print '\nRandom not defined\n'

    return None


def gaussian_random_draw( mu=0.0, sigma=1.0 ):
    """
    Draw a random sample from a 1D Gaussian distribution
    that has mean mu and standard deviation sigma.
    """
    
    return np.random.normal( mu, sigma )
