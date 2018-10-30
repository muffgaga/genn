"""GeNNGroups
This module provides classes which automatize model checks and parameter
convesions for GeNN Groups
"""

from six import iteritems
import numpy as np
import genn_wrapper
import model_preprocessor
from model_preprocessor import Variable
from genn_wrapper import VarMode_LOC_HOST_DEVICE_INIT_HOST
from genn_wrapper import (SynapseMatrixConnectivity_SPARSE,
                          SynapseMatrixConnectivity_YALE,
                          SynapseMatrixConnectivity_RAGGED,
                          SynapseMatrixConnectivity_BITMASK,
                          SynapseMatrixConnectivity_DENSE,
                          SynapseMatrixWeight_INDIVIDUAL,
                          SynapseMatrixWeight_INDIVIDUAL_PSM)


class Group(object):

    """Parent class of NeuronGroup, SynapseGroup and CurrentSource"""

    def __init__(self, name):
        """Init Group

        Args:
        name    --  string name of the Group
        """
        self.name = name
        self.vars = {}
        self.extra_global_params = {}

    def set_var(self, var_name, values):
        """Set values for a Variable

        Args:
        var_name    --  string with the name of the variable
        values      --  iterable or a single value
        """
        self.vars[var_name].set_values(values)

    def _add_extra_global_param(self, param_name, param_values,
                                model, auto_alloc=True):
        """Add extra global parameter

        Args:
        param_name      --  string with the name of the extra global parameter
        param_values    --  iterable or a single value
        model           --  instance of the model
        auto_alloc      --  boolean whether the extra global parameter
                            should be allocated. Defaults to true.
        """
        pnt = list(model.get_extra_global_params())
        param_type = None
        for pn, pt in pnt:
            if pn == param_name:
                param_type = pt
                break

        egp = Variable(param_name, param_type, param_values)
        egp.needs_allocation = auto_alloc

        self.extra_global_params[param_name] = egp

    def _assign_external_pointer(self, slm, scalar, var_name, var_size, var_type):
        """Assign a variable to an external numpy array

        Args:
        slm         --  SharedLibraryModel instance for acccessing variables
        scalar      --  string containing type to use inplace of scalar
        var_name    --  string a fully qualified name of the variable to assign
        var_size    --  int the size of the variable
        var_type    --  string type of the variable. The supported types are
                        char, unsigned char, short, unsigned short, int,
                        unsigned int, long, unsigned long, long long,
                        unsigned long long, float, double, long double
                        and scalar.

        Returns numpy array of type var_type

        Raises ValueError if variable type is not supported
        """

        internal_var_name = var_name + self.name
        if var_type == "scalar":
            if scalar == "float":
                return slm.assign_external_pointer_array_f(
                    internal_var_name, var_size)
            elif scalar == "double":
                return slm.assign_external_pointer_array_d(
                    internal_var_name, var_size)
            elif scalar == "long double":
                return slm.assign_external_pointer_array_ld(
                    internal_var_name, var_size)
        elif var_type == "char":
            return slm.assign_external_pointer_array_c(
                internal_var_name, var_size)
        elif var_type == "unsigned char":
            return slm.assign_external_pointer_array_uc(
                internal_var_name, var_size)
        elif var_type == "short":
            return slm.assign_external_pointer_array_s(
                internal_var_name, var_size)
        elif var_type == "unsigned short":
            return slm.assign_external_pointer_array_us(
                internal_var_name, var_size)
        elif var_type == "int":
            return slm.assign_external_pointer_array_i(
                internal_var_name, var_size)
        elif var_type == "unsigned int":
            return slm.assign_external_pointer_array_ui(
                internal_var_name, var_size)
        elif var_type == "long":
            return slm.assign_external_pointer_array_l(
                internal_var_name, var_size)
        elif var_type == "unsigned long":
            return slm.assign_external_pointer_array_ul(
                internal_var_name, var_size)
        elif var_type == "long long":
            return slm.assign_external_pointer_array_ll(
                internal_var_name, var_size)
        elif var_type == "unsigned long long":
            return slm.assign_external_pointer_array_ull(
                internal_var_name, var_size)
        elif var_type == "float":
            return slm.assign_external_pointer_array_f(
                internal_var_name, var_size)
        elif var_type == "double":
            return slm.assign_external_pointer_array_d(
                internal_var_name, var_size)
        elif var_type == "long double":
            return slm.assign_external_pointer_array_ld(
                internal_var_name, var_size)
        else:
            raise TypeError("unsupported var_type '{}'".format(var_type))

    def _load_vars(self, slm, scalar, size=None, var_dict=None):
        # If no size is specified, use standard size
        if size is None:
            size = self.size

        # If no variable dictionary is specified, use standard one
        if var_dict is None:
            var_dict = self.vars

        # Loop through variables
        for var_name, var_data in iteritems(var_dict):
            # Get view
            var_data.view = self._assign_external_pointer(slm, scalar,
                                                          var_name, size,
                                                          var_data.type)

            # If manual initialisation is required, copy over variables
            if var_data.init_required:
                var_data.view[:] = var_data.values

    def _load_egp(self, slm, scalar, egp_dict=None):
        # If no EGP dictionary is specified, use standard one
        if egp_dict is None:
            egp_dict = self.extra_global_params

        # Loop through extra global params
        for egp_name, egp_data in iteritems(egp_dict):
            # if auto allocation is not enabled, let the user care about
            # allocation and initialization of the EGP
            if egp_data.needs_allocation:
                slm.allocate_extra_global_param(self.name, egp_name,
                                                len(egp_data.values))
                egp_data.view = self._assign_external_pointer(
                    slm, scalar, egp_name, len(egp_data.values),
                    egp_data.type[:-1])
                if egp_data.init_required:
                    egp_data.view[:] = egp_data.values

class NeuronGroup(Group):

    """Class representing a group of neurons"""

    def __init__(self, name):
        """Init NeuronGroup

        Args:
        name    --  string name of the group
        """
        super(NeuronGroup, self).__init__(name)
        self.neuron = None
        self.spikes = None
        self.spike_count = None
        self.spike_que_ptr = [0]
        self.is_spike_source_array = False
        self._max_delay_steps = 0

    @property
    def current_spikes(self):
        """Current spikes from GeNN"""
        offset = self.spike_que_ptr[0] * self.size
        return self.spikes[
            offset:offset + self.spike_count[self.spike_que_ptr[0]]]

    @property
    def delay_slots(self):
        """Maximum delay steps needed for this group"""
        return self.pop.get_num_delay_slots()

    @property
    def size(self):
        return self.pop.get_num_neurons()

    def set_neuron(self, model, param_space, var_space):
        """Set neuron, its parameters and initial variables

        Args:
        model       --  type as string of intance of the model
        param_space --  dict with model parameters
        var_space   --  dict with model variables
        """
        (self.neuron, self.type, self.param_names, self.params,
         self.var_names, self.vars) = model_preprocessor.prepare_model(
             model, param_space, var_space,
             model_family=genn_wrapper.NeuronModels)

        if self.type == "SpikeSourceArray":
            self.is_spike_source_array = True

    def add_to(self, nn_model, num_neurons):
        """Add this NeuronGroup to the GeNN NNmodel

        Args:
        nn_model    --  GeNN NNmodel
        num_neurons --  int number of neurons
        """
        add_fct = getattr(nn_model, "add_neuron_population_" + self.type)

        var_ini = model_preprocessor.var_space_to_vals(self.neuron, self.vars)
        self.pop = add_fct(self.name, num_neurons, self.neuron,
                           self.params, var_ini)

        for var_name, var in iteritems(self.vars):
            if var.init_required:
                self.pop.set_var_mode(var_name,
                                      VarMode_LOC_HOST_DEVICE_INIT_HOST)

    def add_extra_global_param(self, param_name, param_values):
        """Add extra global parameter

        Args:
        param_name      --  string with the name of the extra global parameter
        param_values    --  iterable or a single value
        """
        self._add_extra_global_param(param_name, param_values, self.neuron)

    def load(self, slm, scalar):
        """Loads neuron group

        Args:
        slm --  SharedLibraryModel instance for acccessing variables
        """

        slm.init_neuron_pop_io(self.name)
        self.spikes = self._assign_external_pointer(
            slm, scalar, "glbSpk", self.size * self.delay_slots, "unsigned int")
        self.spike_count = self._assign_external_pointer(
            slm, scalar, "glbSpkCnt", self.delay_slots, "unsigned int")
        if self.delay_slots > 1:
            self.spike_que_ptr = slm.assign_external_pointer_single_ui(
                "spkQuePtr" + self.name)

        # Load neuron state variables
        self._load_vars(slm, scalar)

        # Load neuron extra global params
        self._load_egp(slm, scalar)

class SynapseGroup(Group):

    """Class representing synaptic connection between two groups of neurons"""

    def __init__(self, name):
        """Init SynapseGroup

        Args:
        name    --  string name of the group
        """
        self.connections_set = False
        super(SynapseGroup, self).__init__(name)
        self.w_update = None
        self.postsyn = None
        self.src = None
        self.trg = None
        self.psm_vars = {}
        self.pre_vars = {}
        self.post_vars = {}
        self.connectivity_initialiser = None

    @property
    def num_synapses(self):
        """Number of synapses in group"""
        if self.is_dense:
            return self.trg.size * self.src.size
        elif self.is_yale or self.is_ragged:
            return self._num_synapses

    @property
    def weight_update_var_size(self):
        """Size of each weight update variable"""
        if self.is_dense:
            return self.trg.size * self.src.size
        elif self.is_yale:
            return self._num_synapses
        elif self.is_ragged:
            return self.max_row_length * self.src.size

    @property
    def max_row_length(self):
        return self.pop.get_max_connections()

    def set_psm_var(self, var_name, values):
        """Set values for a postsynaptic model variable

        Args:
        var_name    --  string with the name of the
                        postsynaptic model variable
        values      --  iterable or a single value
        """
        self.psm_vars[var_name].set_values(values)

    def set_pre_var(self, var_name, values):
        """Set values for a presynaptic variable

        Args:
        var_name    --  string with the name of the presynaptic variable
        values      --  iterable or a single value
        """
        self.pre_vars[var_name].set_values(values)

    def set_post_var(self, var_name, values):
        """Set values for a postsynaptic variable

        Args:
        var_name    --  string with the name of the presynaptic variable
        values      --  iterable or a single value
        """
        self.post_vars[var_name].set_values(values)

    def set_weight_update(self, model, param_space,
                          var_space, pre_var_space, post_var_space):
        """Set weight update model, its parameters and initial variables

        Args:
        model           --  type as string of intance of the model
        param_space     --  dict with model parameters
        var_space       --  dict with model variables
        pre_var_space   --  dict with model presynaptic variables
        post_var_space  --  dict with model postsynaptic variables
        """
        (self.w_update, self.wu_type, self.wu_param_names, self.wu_params,
         self.wu_var_names, var_dict, self.wu_pre_var_names, pre_var_dict,
         self.wu_post_var_names, post_var_dict) =\
             model_preprocessor.prepare_model(
                 model, param_space, var_space, pre_var_space,
                 post_var_space, model_family=genn_wrapper.WeightUpdateModels)

        self.vars.update(var_dict)
        self.pre_vars.update(pre_var_dict)
        self.post_vars.update(post_var_dict)

    def set_post_syn(self, model, param_space, var_space):
        """Set postsynaptic model, its parameters and initial variables

        Args:
        model       --  type as string of intance of the model
        param_space --  dict with model parameters
        var_space   --  dict with model variables
        """
        (self.postsyn, self.ps_type, self.ps_param_names, self.ps_params,
         self.ps_var_names, var_dict) = model_preprocessor.prepare_model(
             model, param_space, var_space,
             model_family=genn_wrapper.PostsynapticModels)

        self.psm_vars.update(var_dict)

    def get_var_values(self, var_name):
        var_view = self.vars[var_name].view

        if self.is_dense or self.is_yale:
            return var_view
        elif self.is_ragged:
            # Create array containing the index where each row starts in ind
            row_start_idx = np.arange(0, self.weight_update_var_size,
                                      self.max_row_length)

            # Build list of subviews representing each row
            rows = [var_view[i:i + r]
                    for i, r in zip(row_start_idx, self.row_lengths)]

            # Stack all rows together into single array
            return np.hstack(rows)
        else:
            raise Exception("Matrix format not supported")

    @property
    def is_connectivity_init_required(self):
        return self.connectivity_initialiser is None

    @property
    def matrix_type(self):
        """Type of the projection matrix"""
        return self._matrix_type

    @matrix_type.setter
    def matrix_type(self, matrix_type):
        self._matrix_type = getattr(genn_wrapper,
                                    "SynapseMatrixType_" + matrix_type)

    @property
    def is_yale(self):
        """Tests whether synaptic connectivity uses Yale format"""
        return (self._matrix_type & SynapseMatrixConnectivity_YALE) != 0

    @property
    def is_ragged(self):
        """Tests whether synaptic connectivity uses Ragged format"""
        return (self._matrix_type & SynapseMatrixConnectivity_RAGGED) != 0

    @property
    def is_bitmask(self):
        """Tests whether synaptic connectivity uses Bitmask format"""
        return (self._matrix_type & SynapseMatrixConnectivity_BITMASK) != 0

    @property
    def is_dense(self):
        """Tests whether synaptic connectivity uses dense format"""
        return (self._matrix_type & SynapseMatrixConnectivity_DENSE) != 0

    @property
    def has_individual_synapse_vars(self):
        """Tests whether synaptic connectivity has individual weights"""
        return (self._matrix_type & SynapseMatrixWeight_INDIVIDUAL) != 0

    @property
    def has_individual_postsynaptic_vars(self):
        """Tests whether synaptic connectivity has
        individual postsynaptic model variables"""
        return (self._matrix_type & SynapseMatrixWeight_INDIVIDUAL_PSM) != 0

    def set_sparse_connections(self, pre_indices, post_indices):
        """Set yale or ragged foramt connections between two groups of neurons

        Args:
        pre_indices     --  ndarray of presynaptic indices
        post_indices    --  ndarray of postsynaptic indices
        """
        if self.is_yale or self.is_ragged:
            # Lexically sort indices
            self.synapse_order = np.lexsort((post_indices, pre_indices))
       
            # Count synapses
            self._num_synapses = len(post_indices)
           
            # Count the number of synapses in each row
            row_lengths = np.bincount(pre_indices, minlength=self.src.size)
            row_lengths = row_lengths.astype(np.uint32)
            
            # Use maximum for max connections
            max_row_length = int(np.amax(row_lengths))
            self.pop.set_max_connections(max_row_length)
            
            # Set ind to sorted postsynaptic indices
            self.ind = post_indices[self.synapse_order]

            # If format is yale
            if self.is_yale:
                # Calculate cumulative sium
                self.indInG = np.cumsum(row_lengths, dtype=np.uint32)
                self.indInG = np.insert(self.indInG, 0, 0)

                # Check validity of data structure
                assert len(self.indInG) == (self.src.size + 1)
                assert self.indInG[-1] == self._num_synapses
            # Otherwise if it's ragged
            else:
                # Cache the row lengths
                self.row_lengths = row_lengths

                assert len(self.row_lengths) == self.src.size
        else:
            raise Exception("set_sparse_connections only supports"
                            "ragged and yale format sparse connectivity")

        self.connections_set = True

    def set_connected_populations(self, source, target):
        """Set two groups of neurons connected by this SynapseGroup

        Args:
        source   -- string name of the presynaptic neuron group
        target   -- string name of the postsynaptic neuron group
        """
        self.src = source
        self.trg = target

    def add_to(self, nn_model, delay_steps):
        """Add this SynapseGroup to the GeNN NNmodel

        Args:
        nn_model -- GeNN NNmodel
        """
        add_fct = getattr(
            nn_model,
            ("add_synapse_population_" + self.wu_type + "_" + self.ps_type))

        wu_var_ini = model_preprocessor.var_space_to_vals(
            self.w_update, {vn: self.vars[vn]
                            for vn in self.wu_var_names})

        wu_pre_var_ini = model_preprocessor.pre_var_space_to_vals(
            self.w_update, {vn: self.pre_vars[vn]
                            for vn in self.wu_pre_var_names})

        wu_post_var_ini = model_preprocessor.post_var_space_to_vals(
            self.w_update, {vn: self.post_vars[vn]
                            for vn in self.wu_post_var_names})

        ps_var_ini = model_preprocessor.var_space_to_vals(
            self.postsyn, {vn: self.psm_vars[vn]
                           for vn in self.ps_var_names})

        # Use unitialised connectivity initialiser if none has been set
        connect_init = (genn_wrapper.uninitialised_connectivity()
                        if self.connectivity_initialiser is None
                        else self.connectivity_initialiser)
        self.pop = add_fct(self.name, self.matrix_type, delay_steps,
                           self.src.name, self.trg.name, self.w_update,
                           self.wu_params, wu_var_ini, wu_pre_var_ini,
                           wu_post_var_ini, self.postsyn, self.ps_params,
                           ps_var_ini, connect_init)

        # Mark all weight update model state variables
        # that require initialising on host
        for var_name, var in iteritems(self.vars):
            if var.init_required:
                self.pop.set_wuvar_mode(var_name,
                                        VarMode_LOC_HOST_DEVICE_INIT_HOST)


        # Mark all weight update model presynaptic state
        # variables that require initialising on host
        for var_name, var in iteritems(self.pre_vars):
            if var.init_required:
                self.pop.set_wupre_var_mode(var_name,
                                            VarMode_LOC_HOST_DEVICE_INIT_HOST)

        # Mark all weight update model postsynaptic state
        # variables that require initialising on host
        for var_name, var in iteritems(self.post_vars):
            if var.init_required:
                self.pop.wu_post_var_names(var_name,
                                           VarMode_LOC_HOST_DEVICE_INIT_HOST)

        # Mark all postsynaptic model state variables
        # that require initialising on host
        for var_name, var in iteritems(self.psm_vars):
            if var.init_required:
                self.pop.set_psvar_mode(var_name,
                                        VarMode_LOC_HOST_DEVICE_INIT_HOST)

    def add_extra_global_param(self, param_name, param_values):
        """Add extra global parameter

        Args:
        param_name   -- string with the name of the extra global parameter
        param_values -- iterable or a single value
        """
        self._add_extra_global_param(param_name, param_values, self.w_update)

    def load(self, slm, scalar):
        slm.init_synapse_pop_io(self.name)

        # If synapse population has non-dense connectivity which
        # requires initialising manually
        if not self.is_dense and self.is_connectivity_init_required:
            # If data is available
            if self.connections_set:
                if self.is_yale:
                    # Allocate memory for Yale data structure
                    slm.allocate_yale_proj(self.name, self.num_synapses)

                    # Get pointers to yale data structure members
                    ind = slm.assign_external_yale_ind(self.name,
                                                       self.num_synapses)
                    indInG = slm.assign_external_yale_ind_in_g(self.name,
                                                               self.src.size)

                    # Copy connection data in
                    ind[:] = self.ind
                    indInG[:] = self.indInG
                elif self.is_ragged:
                    # Get pointers to ragged data structure members
                    ind = slm.assign_external_ragged_ind(
                        self.name, self.weight_update_var_size)
                    row_length = slm.assign_external_ragged_row_length(
                        self.name, self.src.size)

                    # Copy in row length
                    row_length[:] = self.row_lengths

                    # Create array containing the index where each row starts in ind
                    row_start_idx = np.arange(0, self.weight_update_var_size,
                                              self.max_row_length)

                    # Loop through ragged matrix rows
                    syn = 0
                    for i, r in zip(row_start_idx, self.row_lengths):
                        # Copy row from non-padded indices into correct location
                        ind[i:i + r] = self.ind[syn:syn + r]
                        syn += r
                else:
                    raise Exception("Matrix format not supported")
            else:
                raise Exception("For sparse projections, the connections"
                                "must be set before loading a model")

        # If population has individual synapse variables
        if self.has_individual_synapse_vars:
            # If weights are in dense or yale format
            if self.is_dense or self.is_yale:
                # Loop through weight update model state variables
                for var_name, var_data in iteritems(self.vars):
                    size = self.weight_update_var_size

                    # Get view
                    var_data.view = self._assign_external_pointer(
                        slm, scalar, var_name, size, var_data.type)

                    # If variable requires initialisation
                    if var_data.init_required:
                        # If connectivity is in Yale format, copy variables
                        # into view, sorting to match GeNN order
                        if self.is_yale:
                            var_data.view[:] = var_data.values[self.synapse_order]
                        # Otherwise, if connectivity is dense,
                        # copy variables  directly into view
                        # **NOTE** we assume order is row-major
                        else:
                            var_data.view[:] = var_data.values

            # Otherwise, if weights are in ragged format
            elif self.is_ragged:
                # Create array containing the index where each row starts in ind
                row_start_idx = np.arange(0, self.weight_update_var_size,
                                          self.max_row_length)

                # Loop through weight update model state variables
                for var_name, var_data in iteritems(self.vars):
                    size = self.weight_update_var_size

                    # Get view
                    var_data.view = self._assign_external_pointer(
                        slm, scalar, var_name, size, var_data.type)

                    # If variable requires initialisation
                    if var_data.init_required:
                        # Sort variable to match GeNN order
                        sorted_var = var_data.values[self.synapse_order]

                        # Loop through ragged matrix rows
                        syn = 0
                        for i, r in zip(row_start_idx, self.row_lengths):
                            # Copy row from non-padded indices into correct location
                            var_data.view[i:i + r] = sorted_var[syn:syn + r]
                            syn += r
            else:
                raise Exception("Matrix format not supported")


        # Load weight update model presynaptic variables
        self._load_vars(slm, scalar, self.src.size, self.pre_vars)

        # Load weight update model postsynaptic variables
        self._load_vars(slm, scalar, self.trg.size, self.post_vars)

        # Load postsynaptic update model variables
        if self.has_individual_postsynaptic_vars:
            self._load_vars(slm, scalar, self.trg.size, self.psm_vars)


class CurrentSource(Group):

    """Class representing a current injection into a group of neurons"""

    def __init__(self, name):
        """Init CurrentSource

        Args:
        name -- string name of the current source
        """
        super(CurrentSource, self).__init__(name)
        self.current_source_model = None
        self.target_pop = None

    @property
    def size(self):
        """Number of neuron in the injected population"""
        return self.target_pop.size

    @size.setter
    def size(self, _):
        pass

    def set_current_source_model(self, model, param_space, var_space):
        """Set curront source model, its parameters and initial variables

        Args:
        model       --  type as string of intance of the model
        param_space --  dict with model parameters
        var_space   --  dict with model variables
        """
        (self.current_source_model, self.type, self.param_names, self.params,
         self.var_names, self.vars) = model_preprocessor.prepare_model(
             model, param_space, var_space,
             model_family=genn_wrapper.CurrentSourceModels)

    def add_to(self, nn_model, pop):
        """Inject this CurrentSource into population and
        add it to the GeNN NNmodel

        Args:
        pop         --  instance of NeuronGroup into which this CurrentSource
                        should be injected
        nn_model    --  GeNN NNmodel
        """
        add_fct = getattr(nn_model, "add_current_source_" + self.type)
        self.target_pop = pop

        var_ini = model_preprocessor.varSpaceToVarValues(
            self.current_source_model, self.vars)
        self.pop = add_fct(self.name, self.current_source_model, pop.name,
                           self.params, var_ini)

        for var_name, var in iteritems(self.vars):
            if var.init_required:
                self.pop.set_var_mode(var_name,
                                      VarMode_LOC_HOST_DEVICE_INIT_HOST)

    def add_extra_global_param(self, param_name, param_values):
        """Add extra global parameter

        Args:
        param_name   -- string with the name of the extra global parameter
        param_values -- iterable or a single value
        """
        self._add_extra_global_param(param_name, param_values,
                                     self.current_source_model)

    def load(self, slm, scalar):
        slm.init_current_source_io(self.name)

        # Load current source variables
        self._load_vars(slm, scalar)

        # Load current source extra global parameters
        self._load_egp(slm, scalar)
