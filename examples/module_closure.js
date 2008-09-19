/**
 * This is documentation for a file that uses the module pattern to provide
 * namespacing.
 *
 * Since the comment is block is followed immediately by something that looks
 * like it could be a function, we explicitly name the module.  This also
 * includes dependencies and other tags.
 *
 * @module ModuleClosure
 * @author Jonathan Tang
 * @license BSD
 * @version 0.1.0
 * @dependency module.js
 */
(function () {

var ModuleClosure = this.ModuleClosure = {

    /**
     * The auto-naming can pick up functions defined as fields of an object,
     * as is common with classes and the module pattern.
     */
    the_first_function: function(arg1, arg2) {

    },

    /**
     * And you can elaborate with parameter tags.  Note that tags must come
     * after the main doc description.
     *
     * @param elem {JQuery} JQuery collection to operate on.
     * @param method {Function(DOM)} Function to invoke on each element.
     * @returns {Array<String>} Some property of the elements.
     */
    the_second_function: function(elem, method) {

    }

};

})();
