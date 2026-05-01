<script setup>
import { computed, onMounted, ref } from "vue";

const requiredColumns = ["username", "comment", "is_reply"];
const csvAssetPath = "/comentarios_com_replies.csv";
const minUniqueMentionsToParticipate = 2;

const rawRows = ref([]);
const parseError = ref("");
const isLoading = ref(true);
const winnersCount = ref(1);
const usernameSearch = ref("");
const winners = ref([]);
const isDrawing = ref(false);
const suspenseName = ref("");

function parseCsv(text) {
  const rows = [];
  let row = [];
  let value = "";
  let inQuotes = false;

  for (let index = 0; index < text.length; index += 1) {
    const char = text[index];
    const nextChar = text[index + 1];

    if (char === '"' && inQuotes && nextChar === '"') {
      value += '"';
      index += 1;
      continue;
    }

    if (char === '"') {
      inQuotes = !inQuotes;
      continue;
    }

    if (char === "," && !inQuotes) {
      row.push(value);
      value = "";
      continue;
    }

    if ((char === "\n" || char === "\r") && !inQuotes) {
      if (char === "\r" && nextChar === "\n") {
        index += 1;
      }

      row.push(value);
      if (row.some((cell) => cell.trim() !== "")) {
        rows.push(row);
      }
      row = [];
      value = "";
      continue;
    }

    value += char;
  }

  row.push(value);
  if (row.some((cell) => cell.trim() !== "")) {
    rows.push(row);
  }

  if (rows.length === 0) {
    return [];
  }

  const headers = rows[0].map((header) => header.trim());
  return rows.slice(1).map((cells) =>
    Object.fromEntries(headers.map((header, index) => [header, cells[index] ?? ""])),
  );
}

function extractMentions(comment) {
  return [...comment.matchAll(/(?<![\w.])@([A-Za-z0-9._]+)/g)].map((match) =>
    match[1].toLowerCase(),
  );
}

function seededRandom(seedValue) {
  let hash = 2166136261;
  const value = seedValue || `${Date.now()}-${Math.random()}`;

  for (let index = 0; index < value.length; index += 1) {
    hash ^= value.charCodeAt(index);
    hash = Math.imul(hash, 16777619);
  }

  return function nextRandom() {
    hash += 0x6d2b79f5;
    let result = hash;
    result = Math.imul(result ^ (result >>> 15), result | 1);
    result ^= result + Math.imul(result ^ (result >>> 7), result | 61);
    return ((result ^ (result >>> 14)) >>> 0) / 4294967296;
  };
}

function validateRows(rows) {
  const columns = rows.length > 0 ? Object.keys(rows[0]) : [];
  const missing = requiredColumns.filter((column) => !columns.includes(column));
  if (missing.length > 0) {
    throw new Error(`CSV sem colunas obrigatorias: ${missing.join(", ")}`);
  }
}

async function loadCsvAsset() {
  winners.value = [];
  parseError.value = "";
  isLoading.value = true;

  try {
    const response = await fetch(csvAssetPath);
    if (!response.ok) {
      throw new Error(`Nao foi possivel carregar ${csvAssetPath}.`);
    }

    const text = await response.text();
    const rows = parseCsv(text);
    validateRows(rows);
    rawRows.value = rows;
  } catch (error) {
    rawRows.value = [];
    parseError.value = error instanceof Error ? error.message : "Nao foi possivel ler o CSV.";
  } finally {
    isLoading.value = false;
  }
}

const participants = computed(() => {
  const byUsername = new Map();

  for (const row of rawRows.value) {
    const username = String(row.username || "").trim().toLowerCase();
    if (!username) {
      continue;
    }

    const stats =
      byUsername.get(username) ||
      {
        username,
        commentsCount: 0,
        mentionsCount: 0,
        mentionedUsernames: new Set(),
      };

    const mentions = extractMentions(String(row.comment || ""));
    stats.commentsCount += 1;
    stats.mentionsCount += mentions.length;
    mentions.forEach((mention) => stats.mentionedUsernames.add(mention));
    byUsername.set(username, stats);
  }

  return [...byUsername.values()]
    .map((participant) => {
      const uniqueMentionsCount = participant.mentionedUsernames.size;
      const extraChances = Math.floor(uniqueMentionsCount / 2);
      return {
        username: participant.username,
        commentsCount: participant.commentsCount,
        mentionsCount: participant.mentionsCount,
        uniqueMentionsCount,
        extraChances,
        totalChances: 1 + extraChances,
      };
    })
    .filter(
      (participant) =>
        participant.uniqueMentionsCount >= minUniqueMentionsToParticipate,
    )
    .sort((left, right) => {
      if (right.totalChances !== left.totalChances) {
        return right.totalChances - left.totalChances;
      }
      return left.username.localeCompare(right.username);
    });
});

const totalChances = computed(() =>
  participants.value.reduce((total, participant) => total + participant.totalChances, 0),
);

const totalMentions = computed(() =>
  participants.value.reduce((total, participant) => total + participant.mentionsCount, 0),
);

const totalUniqueMentions = computed(() =>
  participants.value.reduce((total, participant) => total + participant.uniqueMentionsCount, 0),
);

const filteredParticipants = computed(() => {
  const search = usernameSearch.value.trim().toLowerCase().replace(/^@/, "");
  if (!search) {
    return participants.value;
  }

  return participants.value.filter((participant) =>
    participant.username.includes(search),
  );
});

function delay(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function drawWinners() {
  if (isDrawing.value) {
    return;
  }

  const count = Math.max(1, Number(winnersCount.value) || 1);
  const available = [...participants.value];
  const selected = [];
  const random = seededRandom("");

  while (selected.length < count && available.length > 0) {
    const weightTotal = available.reduce(
      (total, participant) => total + participant.totalChances,
      0,
    );
    let ticket = random() * weightTotal;
    const winnerIndex = available.findIndex((participant) => {
      ticket -= participant.totalChances;
      return ticket < 0;
    });
    const [winner] = available.splice(Math.max(0, winnerIndex), 1);
    selected.push(winner);
  }

  winners.value = [];
  isDrawing.value = true;

  const pool = participants.value;
  const totalDuration = 3000;
  const startInterval = 60;
  const endInterval = 320;
  const startTime = performance.now();
  let currentInterval = startInterval;

  while (performance.now() - startTime < totalDuration) {
    const pick = pool[Math.floor(Math.random() * pool.length)];
    suspenseName.value = pick ? pick.username : "";
    await delay(currentInterval);
    const progress = Math.min(1, (performance.now() - startTime) / totalDuration);
    currentInterval = startInterval + (endInterval - startInterval) * progress * progress;
  }

  suspenseName.value = "";
  isDrawing.value = false;
  winners.value = selected;
}

onMounted(loadCsvAsset);
</script>

<template>
  <main class="app-shell">
    <section class="hero">
      <p class="eyebrow">Sorteio Comentários do Instagram</p>
      <h1>Sorteio PGDelivery + Pé de Açai</h1>
      <p class="summary">
        Importe o arquivo de comentarios, confira as chances e sorteie ao vivo pelo navegador.
      </p>
    </section>

    <section v-if="isLoading || parseError" class="panel data-source">
      <p v-if="isLoading" class="file-name">Carregando CSV...</p>
      <p v-if="parseError" class="error">{{ parseError }}</p>
    </section>

    <section v-if="participants.length" class="stats-grid">
      <div class="stat">
        <span>Participantes</span>
        <strong>{{ participants.length }}</strong>
      </div>
      <div class="stat">
        <span>Marcacoes</span>
        <strong>{{ totalMentions }}</strong>
      </div>
      <div class="stat">
        <span>Pessoas diferentes</span>
        <strong>{{ totalUniqueMentions }}</strong>
      </div>
      <div class="stat">
        <span>Chances</span>
        <strong>{{ totalChances }}</strong>
      </div>
    </section>

    <section v-if="participants.length" class="panel draw-panel">
      <div class="field-row">
        <label>
          <span>Ganhadores</span>
          <input v-model.number="winnersCount" type="number" min="1" :max="participants.length" />
        </label>
      </div>

      <button
        class="primary-button"
        type="button"
        :disabled="isDrawing"
        @click="drawWinners"
      >
        {{ isDrawing ? "Sorteando..." : "Sortear" }}
      </button>
    </section>

    <section v-if="isDrawing" class="suspense" aria-live="polite">
      <span class="suspense-label">Sorteando</span>
      <div class="suspense-stage">
        <span class="suspense-name" :key="suspenseName">@{{ suspenseName || "..." }}</span>
      </div>
      <div class="suspense-dots">
        <span></span><span></span><span></span>
      </div>
    </section>

    <section v-if="winners.length && !isDrawing" class="winners">
      <h2>Resultado</h2>
      <ol>
        <li v-for="winner in winners" :key="winner.username">
          <strong>@{{ winner.username }}</strong>
          <span>{{ winner.totalChances }} chances</span>
        </li>
      </ol>
    </section>

    <section v-if="participants.length" class="panel table-panel">
      <div class="table-header">
        <h2>Auditoria</h2>
        <span>{{ filteredParticipants.length }} de {{ participants.length }} participantes</span>
      </div>
      <label class="search-field">
        <span>Pesquisar username</span>
        <input
          v-model="usernameSearch"
          type="search"
          placeholder="@usuario"
          autocomplete="off"
        />
      </label>
      <div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Usuario</th>
              <th>Comentarios</th>
              <th>Marcacoes</th>
              <th>Pessoas diferentes</th>
              <th>Extra</th>
              <th>Total</th>
            </tr>
          </thead>
          <tbody>
            <tr v-if="filteredParticipants.length === 0">
              <td class="empty-row" colspan="6">Nenhum usuario encontrado.</td>
            </tr>
            <tr v-for="participant in filteredParticipants" :key="participant.username">
              <td>@{{ participant.username }}</td>
              <td>{{ participant.commentsCount }}</td>
              <td>{{ participant.mentionsCount }}</td>
              <td>{{ participant.uniqueMentionsCount }}</td>
              <td>{{ participant.extraChances }}</td>
              <td>{{ participant.totalChances }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>

    <section class="panel source-panel">
      <div>
        <h2>Código fonte</h2>
        <p>
          O código fonte e todos os arquivos usados neste sorteio estão salvos no
          repositório do projeto.
        </p>
      </div>
      <a
        class="source-link"
        href="https://github.com/ygorazambuja/sorteio-instagram"
        target="_blank"
        rel="noreferrer"
      >
        Abrir repositório
      </a>
    </section>
  </main>
</template>
