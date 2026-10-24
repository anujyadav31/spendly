// main.js — vanilla JS for Spendly

// Ask before submitting any form marked with data-confirm (e.g. delete expense).
document.addEventListener("submit", function (event) {
    var message = event.target.getAttribute("data-confirm");
    if (message && !window.confirm(message)) {
        event.preventDefault();
    }
});
