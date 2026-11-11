(function () {
  var typeSelect = document.getElementById("type-select");
  var categorySelect = document.getElementById("category-select");

  if (typeSelect && categorySelect) {
    var allOptions = Array.prototype.slice.call(categorySelect.options);

    function filterCategories() {
      var type = typeSelect.value;
      var current = categorySelect.value;
      categorySelect.innerHTML = "";
      allOptions.forEach(function (opt) {
        if (!opt.value || opt.getAttribute("data-type") === type) {
          categorySelect.appendChild(opt.cloneNode(true));
        }
      });
      categorySelect.value = current;
    }

    typeSelect.addEventListener("change", filterCategories);
    filterCategories();
  }
})();
