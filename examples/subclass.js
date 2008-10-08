(function() {

/**
 * This is subclass of MyClass.  It's marked explicitly with the 'extends'
 * tag.  
 *
 * @class MySubClass
 * @extends MyClass
 * @requires MyClass
 */
this.MySubClass = ModuleClosure.make_class(MyClass, {

    /**
     * This is the constructor, marked explicitly and presumably called by
     * the {@link #make_class} machinery.
     *
     * @constructor
     * @member MySubClass
     * @param arg1 The first argument
     * @param arg2 The second argument.
     */
    init: function(arg1, arg2) {

    }

    /** 
     * A public method.  
     * @member MySubClass
     */
    public_method: function(arg1, arg2) {}

    /** 
     * A private method 
     * @private
     * @member MySubClass
     * @see #public_method
     */
    private_method: function(args) {}

});

})();

/**
 * This time, we put the module documentation at the bottom (even though that's
 * not really common convention) to test the @fileoverview tag.
 *
 * @fileoverview
 * @author Jonathan Tang
 * @version 0.1.0
 * @dependency module_closure.js
 * @dependency class.js
 */
