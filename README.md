# Sorteio Instagram

Utilitario para exportar as pessoas que comentaram em um post/reel do Instagram e os respectivos comentarios usando `instaloader`.

## Instalar

```bash
uv sync
```

## Usar

Primeiro, salve uma sessao do Instagram. Pode usar o email de login. Isso evita colocar senha no script e reduz bloqueios:

```bash
uv run instaloader -l SEU_EMAIL
```

Depois exporte os comentarios:

```bash
uv run instagram-comments "https://www.instagram.com/p/SHORTCODE/" --login SEU_EMAIL --output comentarios.csv
```

Se houver apenas uma sessao salva, o script usa essa sessao automaticamente:

```bash
uv run instagram-comments "https://www.instagram.com/p/SHORTCODE/" --output comentarios.csv
```

Tambem funciona com reels:

```bash
uv run instagram-comments "https://www.instagram.com/reel/SHORTCODE/" --login SEU_EMAIL -o comentarios.csv
```

O CSV gerado inclui:

- `username`
- `comment`
- `created_at_utc`
- `likes_count`
- `comment_id`
- `parent_comment_id`
- `is_reply`

Por padrao, apenas comentarios principais sao exportados. Para incluir respostas a comentarios:

```bash
uv run instagram-comments "https://www.instagram.com/p/SHORTCODE/" --login SEU_EMAIL --include-replies
```

Se o Instagram retornar erro no endpoint mobile de comentarios, force o backend GraphQL:

```bash
uv run instagram-comments "https://www.instagram.com/p/SHORTCODE/" --login SEU_EMAIL --comments-backend graphql
```

## Observacoes

O Instagram pode limitar ou bloquear consultas. A sessao do Instaloader fica salva com o identificador usado no login, por exemplo `session-ygoazambuja` ou `session-email@dominio.com`. Use esse mesmo valor em `--login`, ou omita `--login` quando houver apenas uma sessao salva.

## Sorteio

Depois de baixar os comentarios, o sorteio roda apenas em cima do CSV local:

```bash
uv run instagram-sorteio -i comentarios_com_replies.csv -o participantes_sorteio.csv
```

A regra aplicada e agregada por pessoa:

- para participar, a pessoa precisa ter marcado pelo menos 2 pessoas diferentes;
- cada participante elegivel tem 1 chance base;
- a cada 2 pessoas diferentes marcadas pela mesma pessoa, ela ganha 1 chance extra;
- marcar a mesma pessoa mais de uma vez nao aumenta a contagem de pessoas diferentes;
- quem nao marcou ninguem ou marcou menos de 2 pessoas diferentes fica fora do sorteio;
- quando sobra 1 pessoa marcada sem par, ela nao aumenta a chance.

O arquivo `participantes_sorteio.csv` mostra `comments_count`, `mentions_count`, `unique_mentions_count`, `extra_chances` e `total_chances` para auditoria. Para reproduzir exatamente o mesmo sorteio, use uma seed:

```bash
uv run instagram-sorteio -i comentarios_com_replies.csv --seed minha-seed
```

## App web

O app Vue/Vite roda o sorteio no navegador usando o CSV empacotado como asset em `public/comentarios_com_replies.csv`. Ele nao faz login, nao acessa Instagram e nao envia o CSV para backend.

Para rodar localmente:

```bash
npm install
npm run dev
```

Para gerar o build de producao:

```bash
npm run build
```

Para atualizar o CSV usado no site, substitua `public/comentarios_com_replies.csv` pelo CSV final antes do deploy.

Deploy na Vercel:

```bash
npm run build
vercel
```

A configuracao em `vercel.json` usa `npm run build` e publica a pasta `dist`.
