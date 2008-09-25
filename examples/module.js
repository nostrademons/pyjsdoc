/**
 * This is the module documentation.  It looks exactly like a JavaDoc comment:
 * introduced by a slash-star-star, closed by a star-slash, with internal stars
 * ignored.  The first paragraph appears as a summary in the full module list.
 *
 * PyJSDoc determines that this comment is the module documentation because
 * it's the first comment within the file that is not (implicitly or explicitly)
 * attached to a function or class.  It's possible to override this with an
 * \@fileoverview tag, as shown in module_closure.js.
 *
 * Also note the escaping of the \@ sign above; this is necessary to avoid
 * interpreting it as a tag.  PyJSDoc is fully extensible, and so it'll
 * recognize tags beyond those built in.
 */

/**
 * This is documentation for the first method.  PyJSDoc automatically picks up
 * the name and arguments because the comment is immediately followed by a
 * function(arg1, arg2) ... line.  There cannot be any blank lines between the
 * comment and the opening line of the function.
 */
function the_first_function(arg1, arg2) 
{

};

/** This is the documentation for the second function. */
function the_second_function(arg1, arg2) {

};

/**
 * This is the documentation for the third function.
 *
 * The code to detect the function name and arguments is fairly lenient: as long
 * as "function name(arg1, arg2)" appears on the next line, it'll pick it up.
 */
window.the_third_function = function(arg1, arg2) {

};

/**
 * This is the documentation for the fourth function.
 *
 * Since the function being documented is itself generated from another
 * function, its name needs to be specified explicitly. using the @function tag
 *
 * @function not_auto_discovered
 * @param {String} arg1 The first argument.
 * @param {Int} arg2 The second argument.
 */
window.not_auto_discovered = higher_order_programming(the_third_function);

function undocumented_functions_are_not_picked_up() {

};
