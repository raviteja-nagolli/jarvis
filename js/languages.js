window.JarvisLanguages = (() => {
  const languages = [
    { code: "en-IN", name: "English", locale: "en-IN" },
    { code: "kn-IN", name: "ಕನ್ನಡ · Kannada", locale: "kn-IN" },
    { code: "hi-IN", name: "हिन्दी · Hindi", locale: "hi-IN" },
    { code: "ta-IN", name: "தமிழ் · Tamil", locale: "ta-IN" },
    { code: "te-IN", name: "తెలుగు · Telugu", locale: "te-IN" }
  ];

  function populate(select, initialCode) {
    select.replaceChildren(...languages.map((language) => {
      const option = document.createElement("option");
      option.value = language.code;
      option.textContent = language.name;
      option.selected = language.code === initialCode;
      return option;
    }));
  }

  return { languages, populate };
})();