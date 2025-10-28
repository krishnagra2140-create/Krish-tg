async function fetchLogs() {
  const response = await fetch("/logs");
  const data = await response.json();
  const logBox = document.getElementById("logs");
  logBox.innerHTML = data.map(l => `<div>${l}</div>`).join("");
  logBox.scrollTop = logBox.scrollHeight;
}
setInterval(fetchLogs, 2000);
