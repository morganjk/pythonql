from pythonql.PQTuple import PQTuple
from pythonql.PQTable import PQTable
import json

def str_dec(string):
    res = ""
    prev_slash = False
    for ch in string:
        if ch == chr(92):
            if not prev_slash:
                prev_slash = True
            else:
                res += ch
                prev_slash = False
        else:
            prev_slash = False
            res += ch
    return res

# isList predicate for path expressions
def isList(x):
  return (hasattr(x,'__iter__') and not 
          hasattr(x,'keys') and not
          isinstance(x,str))

# isMap predicate for path expression
def isMap(x):
  return hasattr(x,'keys')

# Implement a child step on some collection or map
def PQChildPath (coll):
  if isList(coll):
    for i in coll:
      if isList(i):
        for j in i:
          yield j
      elif isMap(i):
        for j in i.keys():
          yield i[j]
  if isMap(coll):
    for i in coll.keys():
      yield coll[i]

# Implement a descendents path on some collection or map
def PQDescPath(coll):
  stack = []
  if isList(coll):
    stack = [i for i in coll]
  elif isMap(coll):
    stack = list(coll.values())
  while stack:
    i = stack.pop()
    yield i
    if isList(i):
      [stack.append(j) for j in i[1:]]
      if isList(i[0]):
        stack.extend([ci for ci in i[0]])
      elif isMap(i[0]):
        stack.extend(i[0].values())
      yield i[0]
    elif isMap(i):
      keys = list(i.keys())
      [stack.append(i[j]) for j in keys[1:]]
      yield i[keys[0]]

#Implements a predicate step on a collection
def PQPred(coll, pred):
  pred = str_dec(pred)
  if isList(coll):
    return PQPred_list(coll,pred)
  elif isMap(coll):
    return PQPred_map(coll,pred)

def PQPred_list(coll,pred):
  lcs = locals()
  for i in coll:
    lcs.update({'item':i})
    if eval(pred,globals(),lcs):
      yield i

def PQPred_map(coll,pred):
  lcs = locals()
  result = {}
  for (k,v) in coll.items():
    lcs.update({'key':k, 'value':v})
    if eval(pred,globals(),lcs):
      result[k] = v
  return result

def PQTry( try_expr, except_expr, exc, lcs):
  try_expr = str_dec(try_expr)
  except_expr = str_dec(except_expr)
  if exc:
    exc = str_dec(exc)
    try:
      return eval(try_expr,lcs,globals())
    except eval(exc):
      return eval(except_expr,lcs,globals())
  else:
    try:
      return eval(try_expr,lcs,globals())
    except:
      return eval(except_expr,lcs,globals())

# create a table with an empty tuple
def emptyTuple(schema):
  return PQTuple([None] * len(schema), schema)

# Execute the query
def PyQuery( clauses, prior_locs ):
  table = PQTable([])
  table.data.append( emptyTuple([]) )
  for c in clauses:
    table = processClause(c, table, prior_locs)
  return table.data

# Process clauses
def processClause(c, table, prior_locs):
  if c["name"] == "select":
    return processSelectClause(c, table, prior_locs)
  elif c["name"] == "for":
    return processForClause(c, table, prior_locs)
  elif c["name"] == "let":
    return processLetClause(c, table, prior_locs)
  elif c["name"] == "count":
    return processCountClause(c, table, prior_locs)
  elif c["name"] == "where":
    return processWhereClause(c, table, prior_locs)
  elif c["name"] == "groupby":
    return processGroupByClause(c, table, prior_locs)
  elif c["name"] == "orderby":
    return processOrderByClause(c, table, prior_locs)
  elif c["name"] == "window":
    return processWindowClause(c, table, prior_locs)
  else:
    raise Exception("Unknown clause %s encountered" % c[0] )
  
# Process Select clause
# We still keep that feature of generating tuples for now
def processSelectClause(c, table, prior_lcs):
  # Compute the output schema
  select_schema = { (sel[1] if sel[1] else sel[0]) : i 
			for (i,sel) in enumerate(c["select_list"]) }
  # Create a new table that will be filled out by this
  # method
  new_table = PQTable(select_schema)

  # Compile all the expressions
  comp_exprs = [ s[0].lstrip() for s in c["select_list"] ]
  comp_exprs = [ compile(e,'<string>','eval') for e in comp_exprs ]
  for t in table.data:
    # Compute the value of tuple elements
    new_tuple = []
    for (i,sel) in enumerate(c["select_list"]):
      lcs = prior_lcs
      lcs.update(t.getDict())
      new_tuple.append( eval(comp_exprs[i], globals(), lcs))

    # If we have only one element in the select list
    # then the output table will be a sequence of values
    if len(c["select_list"]) == 1:
      new_table.data.append(new_tuple[0])

    # Otherwise we'll create tuples in the output
    else:
      new_table.data.append(PQTuple( new_tuple, select_schema))

  return new_table

# Process the for clause. This clause creates a cartesian
# product of the input table with new sequence
def processForClause(c, table, prior_lcs):
  new_schema = dict(table.schema)
  new_schema[c["var"]] = len(table.schema)
  comp_expr = compile(c["expr"].lstrip(), "<string>", "eval")

  new_table = PQTable( new_schema )
  for t in table.data:
    lcs = prior_lcs
    lcs.update(t.getDict())
    vals = eval(comp_expr, globals(), lcs)
    for v in vals:
      new_t_data = list(t.tuple)
      new_t_data.append(v)
      new_t = PQTuple(new_t_data, new_schema)
      new_table.data.append(new_t)

  return new_table

# Process the let clause. Here we just add a variable to each
# input tuple
def processLetClause(c, table, prior_lcs):
  new_schema = dict(table.schema)
  new_schema[ c["var"]] = len(table.schema)
  comp_expr = compile(c["expr"].lstrip(), "<string>", "eval")
  new_table = PQTable( new_schema )
  for t in table.data:
    lcs = prior_lcs
    lcs.update(t.getDict())
    v = eval(comp_expr, globals(), lcs)
    t.tuple.append(v)
    new_t = PQTuple( t.tuple, new_schema )
    new_table.data.append(new_t)
  return new_table

# Process the count clause. Similar to let, but simpler
def processCountClause(c, table, prior_lcs):
  new_schema = dict(table.schema)
  new_schema[ c["var"]] = len(table.schema)
  new_table = PQTable( new_schema )
  for (i,t) in enumerate(table.data):
    new_t = PQTuple( t.tuple + [i], new_schema )
    new_table.data.append(new_t)
  return new_table

# Process the group-by
def processGroupByClause(c, table, prior_lcs):
  gby_aliases = [g if isinstance(g,str) else g[1]
                                for g in c["groupby_list"]]
  gby_exprs = [g if isinstance(g,str) else g[0]
                                for g in c["groupby_list"]]
  comp_exprs = [compile(e,'<string>','eval') for e in gby_exprs]
  grp_table = {}

  # Group tuples in a hashtable
  for t in table.data:
    lcs = prior_lcs
    lcs.update(t.getDict())
    # Compute the key
    k = tuple( [eval(e,globals(),lcs) for e in comp_exprs] )
    if not k in grp_table:
      grp_table[k] = []
    grp_table[k].append(t)

  # Construct the new table
  # Non-key variables
  non_key_vars = [v for v in table.schema if not v in gby_aliases ]
  new_schema = {v:i for (i,v) in enumerate( gby_aliases + non_key_vars )}
  new_table = PQTable(new_schema)
  for k in grp_table:
    t = PQTuple([None]*len(new_schema), new_schema)
    #Copy over the key
    for (i,v) in enumerate(gby_aliases):
      t[v] = k[i]

    #Every other variable (not in group by list) is turned into a lists
    #First create empty lists
    for v in non_key_vars:
      t[v] = []

    # Now fill in the lists:
    for part_t in grp_table[k]:
      for v in non_key_vars:
        t[v].append( part_t[v] )

    new_table.data.append(t)

  return new_table

# Process where clause
def processWhereClause(c, table, prior_lcs):
  new_table = PQTable(table.schema)
  comp_expr = compile(c["expr"].lstrip(),"<string>","eval")
  for t in table.data:
    lcs = prior_lcs
    lcs.update(t.getDict())
    val = eval(comp_expr, globals(), lcs)
    if val:
      new_table.data.append(t)

  return new_table

# Process the orderby clause
def processOrderByClause(c, table, prior_lcs):
  # Here we do n sorts, n is the number of sort specifications
  # For each sort we first need to compute a sort value (could
  # be some expression)

  sort_exprs = [ compile(os[0].lstrip(),"<string>","eval") for os in c["orderby_list"]]
  sort_rev = [ o[1]=='desc' for o in c["orderby_list"]]

  def computeSortSpec(tup,sort_spec):
    lcs = prior_lcs
    lcs.update(tup.getDict())
    return eval(sort_spec, globals(), lcs)

  sort_exprs.reverse()
  sort_rev.reverse()
  for (i,e) in enumerate(sort_exprs):
    table.data.sort( key = lambda x: computeSortSpec(x,e),
         reverse= sort_rev[i])

  return table
  
# Create the set of variables for a new window
# This is the full set just for convienience, the
# query might not use all of these vars.
# The names of the variables coincide with the
# names in the specification of window clause

def make_window_vars():
  return {"s_curr":None, "s_at":None, "s_prev":None, "s_next":None,
          "e_curr":None, "e_at":None, "e_prev":None, "e_next":None}

# Start variables from a list of variables
all_start_vars = ["s_curr","s_at","s_prev","s_next"]

# Fill in the start vars of the window, given the value list and current index
def fill_in_start_vars(vars, binding_seq, i ):
  vars["s_curr"] = binding_seq[i]
  vars["s_at"] = i
  vars["s_prev"] = binding_seq[i-1] if i>0 else None
  vars["s_next"] = binding_seq[i+1] if i+1<len(binding_seq) else None

# Fill in the end vars of the window, given the values list and current index
def fill_in_end_vars(vars, binding_seq, i ):
  vars["e_curr"] = binding_seq[i]
  vars["e_at"] = i
  vars["e_prev"] = binding_seq[i-1] if i>0 else None
  vars["e_next"] = binding_seq[i+1] if i+1<len(binding_seq) else None

# Check the start condition of the window, i.e. whether we should
# start a new window at this location (without considering tumbling
# windows, that check is done elsewhere).

def check_start_condition(all_vars,clause,locals,var_mapping):
  # we just need to evaluate the when expression 
  # but we need to set up the vars correctly, respecting the visibility
  # conditions
  start_vars = set(all_start_vars).intersection(
		set(var_mapping.keys()) )
  start_bindings = { var_mapping[v] : all_vars[v] for v in start_vars }

  # add the binding to the locals
  locals.update( start_bindings )

  #evaluate the when condition
  return eval( clause["s_when"], globals(), locals )
  
# Check the end condition of the window.

def check_end_condition(vars,clause,locals,var_mapping):
  # If there is no 'when' clause, return False
  if not clause["e_when"]:
    return False

  end_vars = set(vars.keys()).intersection( set(var_mapping.keys()))
  end_binding = { var_mapping[v] : vars[v] for v in end_vars }

  locals.update( end_binding )
  res = eval( clause["e_when"], globals(), locals)

  return res

# Process window clause
def processWindowClause(c, table, prior_lcs):
  # Create a new schema with window variables added
  new_schema = dict(table.schema)
  for v in c["vars"]:
    new_schema[c["vars"][v]] = len(new_schema)

  # Create window variable name mapping
  var_mapping = {}
  for v in c["vars"]:
    var_mapping[v] = c["vars"][v]
		
  new_table = PQTable( new_schema )
  for t in table.data:
    lcs = dict(prior_lcs)
    lcs.update(t.getDict())
    # Evaluate the binding sequence
    binding_seq = list(eval(c["in"], globals(), lcs))

    # Create initial window variables

    # Initialize the windows
    open_windows = []
    closed_windows = []

    # Iterate over the binding sequence
    for (i,v) in enumerate(binding_seq):
      # Try to open a new window
      # in case of tumbling windows, only open a
      # window if there are no open windows
      if not c["tumbling"] or (c["tumbling"] and not open_windows):
        vars = make_window_vars()
        fill_in_start_vars(vars,binding_seq,i)
        if check_start_condition(vars,c,dict(lcs),var_mapping):
          open_windows.append( {"window":[], "vars":vars} )
      
      new_open_windows = []
      #update all open windows, close those that are finished
      for w in open_windows:
        # Add currnt value to the window
        w["window"].append(v)

        fill_in_end_vars(w["vars"],binding_seq,i)

        if check_end_condition(w["vars"],c,dict(lcs),var_mapping):
          closed_windows.append(w)
        else:
          new_open_windows.append(w)
      open_windows = new_open_windows
          
    #close or remove all remaining open windows
    #if only is specified, we ignore non-closed windows
    if not c["only"]:
      closed_windows.extend(open_windows)
    
    # create a new tuple by extending the tuple from previous clauses
    # with the window variables, for each closed window
    for w in closed_windows:
      new_t = PQTuple( t.tuple + [None]*(len(new_schema)-len(table.schema)), new_schema)
      new_t[ var_mapping["var"] ] = w["window"]
      for v in [v for v in w["vars"].keys() if v in var_mapping]:
        new_t[ var_mapping[v] ] = w["vars"][v]
      new_table.data.append(new_t)

  return new_table
