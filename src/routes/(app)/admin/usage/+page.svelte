<script lang="ts">
	import { onMount, getContext } from 'svelte';
	import { user } from '$lib/stores';
	import { getAdminUsageSummary, type AdminUsageModel, type AdminUsageSummary } from '$lib/apis';
	import { goto } from '$app/navigation';

	const i18n = getContext('i18n');

	let loading = true;
	let failed = false;
	let query = '';
	let view: 'models' | 'users' = 'models';
	let sortKey: 'total_tokens' | 'cost_micros' | 'request_count' | 'updated_at' = 'total_tokens';
	let modelSortKey: 'total_tokens' | 'cost_micros' | 'request_count' = 'total_tokens';
	let summary: AdminUsageSummary | null = null;
	let openUserId: string | null = null;

	const formatTokens = (value: number) => new Intl.NumberFormat().format(value || 0);

	const formatMoney = (micros: number) => {
		const usd = (micros || 0) / 1_000_000;
		const digits = usd > 0 && usd < 0.01 ? 4 : 2;
		return usd.toLocaleString(undefined, {
			style: 'currency',
			currency: 'USD',
			minimumFractionDigits: digits,
			maximumFractionDigits: digits
		});
	};

	const formatUpdated = (timestamp: number) =>
		timestamp ? new Date(timestamp * 1000).toLocaleString() : '—';

	const matches = (needle: string, values: Array<string | null | undefined>) =>
		!needle || values.some((value) => (value || '').toLowerCase().includes(needle));

	$: needle = query.trim().toLowerCase();
	$: users = (summary?.users ?? []).filter((row) =>
		matches(needle, [row.user_name, row.user_email, row.user_id])
	);

	$: sortedUsers = [...users].sort((a, b) => (b[sortKey] || 0) - (a[sortKey] || 0));
	$: totalTokens = summary?.totals.total_tokens || 0;

	const share = (tokens: number) => (totalTokens > 0 ? Math.round((tokens / totalTokens) * 100) : 0);

	const modelsFor = (userId: string) =>
		(summary?.models ?? [])
			.filter((row) => row.user_id === userId)
			.sort((a, b) => b.total_tokens - a.total_tokens);

	const topModels = (rows: AdminUsageModel[]) => {
		const grouped = new Map<string, AdminUsageModel>();
		for (const row of rows) {
			const current = grouped.get(row.model);
			if (!current) {
				grouped.set(row.model, { ...row, user_id: '' });
				continue;
			}
			current.request_count += row.request_count;
			current.prompt_tokens += row.prompt_tokens;
			current.completion_tokens += row.completion_tokens;
			current.total_tokens += row.total_tokens;
			current.cost_micros += row.cost_micros;
			current.unpriced_tokens += row.unpriced_tokens;
			current.model_name = current.model_name || row.model_name;
			current.base_model_id = current.base_model_id || row.base_model_id;
		}
		return [...grouped.values()];
	};

	$: modelRows = topModels(summary?.models ?? []).filter((row) =>
		matches(needle, [row.model, row.model_name, row.base_model_id])
	);
	$: sortedModels = [...modelRows].sort((a, b) => (b[modelSortKey] || 0) - (a[modelSortKey] || 0));

	const loadData = async () => {
		loading = true;
		failed = false;
		try {
			summary = await getAdminUsageSummary(localStorage.token ?? '');
		} catch (error) {
			console.error(error);
			failed = true;
			summary = null;
		} finally {
			loading = false;
		}
	};

	onMount(async () => {
		if ($user?.role !== 'admin') {
			await goto('/');
			return;
		}
		await loadData();
	});

	const cards = (data: AdminUsageSummary | null) => [
		{ label: 'Users', value: formatTokens(data?.totals.users ?? 0) },
		{ label: 'Requests', value: formatTokens(data?.totals.request_count ?? 0) },
		{ label: 'Input tokens', value: formatTokens(data?.totals.prompt_tokens ?? 0) },
		{ label: 'Output tokens', value: formatTokens(data?.totals.completion_tokens ?? 0) },
		{ label: 'Total tokens', value: formatTokens(data?.totals.total_tokens ?? 0) },
		{ label: 'Estimated spend', value: formatMoney(data?.totals.cost_micros ?? 0) }
	];
</script>

<div class="mx-auto flex w-full max-w-6xl flex-col gap-5 px-4 py-5 md:px-6">
	<div class="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
		<div class="flex flex-col gap-1">
			<h2 class="text-xl font-medium">{$i18n.t('Usage')}</h2>
			<p class="max-w-xl text-sm text-gray-500">
				{$i18n.t('Lifetime totals. Workspace models also show the base model they call.')}
			</p>
		</div>
		<div class="flex w-fit rounded-xl bg-gray-50 p-1 dark:bg-gray-900">
			<button
				class="rounded-lg px-3 py-1.5 text-sm {view === 'models'
					? 'bg-white text-gray-900 shadow-sm dark:bg-gray-850 dark:text-white'
					: 'text-gray-500'}"
				on:click={() => (view = 'models')}
			>
				{$i18n.t('Models')}
				<span class="tabular-nums text-gray-400">{modelRows.length}</span>
			</button>
			<button
				class="rounded-lg px-3 py-1.5 text-sm {view === 'users'
					? 'bg-white text-gray-900 shadow-sm dark:bg-gray-850 dark:text-white'
					: 'text-gray-500'}"
				on:click={() => (view = 'users')}
			>
				{$i18n.t('People')}
				<span class="tabular-nums text-gray-400">{users.length}</span>
			</button>
		</div>
	</div>

	{#if loading}
		<div class="text-sm text-gray-500">{$i18n.t('Loading...')}</div>
	{:else if failed}
		<div class="text-sm text-red-500">{$i18n.t('Failed to load usage.')}</div>
	{:else}
		<div class="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
			{#each cards(summary) as card}
				<div class="rounded-2xl border border-gray-100 px-3.5 py-3 dark:border-gray-850">
					<div class="text-xs text-gray-500">{card.label}</div>
					<div class="mt-1 text-lg font-medium tracking-tight">{card.value}</div>
				</div>
			{/each}
		</div>

		{#if (summary?.totals.unpriced_tokens ?? 0) > 0}
			<div class="text-xs text-gray-500">
				{formatTokens(summary?.totals.unpriced_tokens ?? 0)}
				{$i18n.t('tokens are counted, but their model has no price, so they are not included in spend.')}
			</div>
		{/if}

		<input
			class="w-full rounded-xl border border-gray-100 bg-transparent px-3 py-2 text-sm outline-none placeholder:text-gray-400 focus:border-gray-300 dark:border-gray-850 dark:focus:border-gray-700"
			bind:value={query}
			placeholder={view === 'models'
				? $i18n.t('Search by model or base model')
				: $i18n.t('Search by name or email')}
		/>

		<div class="overflow-hidden rounded-2xl border border-gray-100 dark:border-gray-850">
			{#if view === 'models'}
				<div class="overflow-x-auto">
					<table class="min-w-[56rem] w-full text-sm">
						<thead class="bg-gray-50 text-xs text-gray-500 dark:bg-gray-900">
							<tr>
								<th class="whitespace-nowrap px-4 py-2.5 text-left font-medium">{$i18n.t('Model')}</th>
								<th class="whitespace-nowrap px-3 py-2.5 text-left font-medium">{$i18n.t('Base model')}</th>
								<th class="whitespace-nowrap px-3 py-2.5 text-right font-medium">
									<button
										class="hover:text-gray-900 dark:hover:text-white {modelSortKey === 'request_count'
											? 'text-gray-900 dark:text-white'
											: ''}"
										on:click={() => (modelSortKey = 'request_count')}
									>
										{$i18n.t('Requests')}
									</button>
								</th>
								<th class="whitespace-nowrap px-3 py-2.5 text-right font-medium">{$i18n.t('Input')}</th>
								<th class="whitespace-nowrap px-3 py-2.5 text-right font-medium">{$i18n.t('Output')}</th>
								<th class="whitespace-nowrap px-3 py-2.5 text-right font-medium">
									<button
										class="hover:text-gray-900 dark:hover:text-white {modelSortKey === 'total_tokens'
											? 'text-gray-900 dark:text-white'
											: ''}"
										on:click={() => (modelSortKey = 'total_tokens')}
									>
										{$i18n.t('Total tokens')}
									</button>
								</th>
								<th class="whitespace-nowrap px-3 py-2.5 text-right font-medium">{$i18n.t('Share')}</th>
								<th class="whitespace-nowrap px-4 py-2.5 text-right font-medium">
									<button
										class="hover:text-gray-900 dark:hover:text-white {modelSortKey === 'cost_micros'
											? 'text-gray-900 dark:text-white'
											: ''}"
										on:click={() => (modelSortKey = 'cost_micros')}
									>
										{$i18n.t('Estimated spend')}
									</button>
								</th>
							</tr>
						</thead>
						<tbody>
							{#if sortedModels.length === 0}
								<tr>
									<td colspan="8" class="px-4 py-10 text-center text-gray-400">
										{$i18n.t('Model totals start with the next request. Older totals have no model split.')}
									</td>
								</tr>
							{:else}
								{#each sortedModels as row (row.model)}
									<tr class="border-t border-gray-100 hover:bg-gray-50/80 dark:border-gray-850 dark:hover:bg-gray-900/60">
										<td class="whitespace-nowrap px-4 py-2.5">
											<div class="font-medium">{row.model_name || row.model}</div>
											{#if row.model_name}
												<div class="font-mono text-[11px] text-gray-400">{row.model}</div>
											{/if}
										</td>
										<td class="whitespace-nowrap px-3 py-2.5">
											{#if row.base_model_id}
												<span
													class="inline-flex max-w-[16rem] truncate rounded-md bg-gray-100 px-1.5 py-0.5 font-mono text-[11px] text-gray-600 dark:bg-gray-800 dark:text-gray-300"
													title={row.base_model_id}
												>
													{row.base_model_id}
												</span>
											{:else}
												<span class="text-xs text-gray-300 dark:text-gray-600">—</span>
											{/if}
										</td>
										<td class="px-3 py-2.5 text-right tabular-nums">{formatTokens(row.request_count)}</td>
										<td class="px-3 py-2.5 text-right tabular-nums text-gray-500">{formatTokens(row.prompt_tokens)}</td>
										<td class="px-3 py-2.5 text-right tabular-nums text-gray-500">{formatTokens(row.completion_tokens)}</td>
										<td class="px-3 py-2.5 text-right font-medium tabular-nums">{formatTokens(row.total_tokens)}</td>
										<td class="px-3 py-2.5">
											<div class="flex items-center justify-end gap-2">
												<div class="h-1.5 w-14 overflow-hidden rounded-full bg-gray-100 dark:bg-gray-800">
													<div
														class="h-full rounded-full bg-gray-800 dark:bg-gray-200"
														style="width: {Math.min(share(row.total_tokens), 100)}%"
													></div>
												</div>
												<span class="w-8 text-right text-xs tabular-nums text-gray-500">{share(row.total_tokens)}%</span>
											</div>
										</td>
										<td class="px-4 py-2.5 text-right tabular-nums">{formatMoney(row.cost_micros)}</td>
									</tr>
								{/each}
							{/if}
						</tbody>
					</table>
				</div>
			{:else}
				<div class="overflow-x-auto">
					<table class="min-w-[56rem] w-full text-sm">
						<thead class="bg-gray-50 text-xs text-gray-500 dark:bg-gray-900">
							<tr>
								<th class="whitespace-nowrap px-4 py-2.5 text-left font-medium">{$i18n.t('User')}</th>
								<th class="whitespace-nowrap px-3 py-2.5 text-right font-medium">
									<button
										class="hover:text-gray-900 dark:hover:text-white {sortKey === 'request_count'
											? 'text-gray-900 dark:text-white'
											: ''}"
										on:click={() => (sortKey = 'request_count')}
									>
										{$i18n.t('Requests')}
									</button>
								</th>
								<th class="whitespace-nowrap px-3 py-2.5 text-right font-medium">{$i18n.t('Input')}</th>
								<th class="whitespace-nowrap px-3 py-2.5 text-right font-medium">{$i18n.t('Output')}</th>
								<th class="whitespace-nowrap px-3 py-2.5 text-right font-medium">
									<button
										class="hover:text-gray-900 dark:hover:text-white {sortKey === 'total_tokens'
											? 'text-gray-900 dark:text-white'
											: ''}"
										on:click={() => (sortKey = 'total_tokens')}
									>
										{$i18n.t('Total tokens')}
									</button>
								</th>
								<th class="whitespace-nowrap px-3 py-2.5 text-right font-medium">{$i18n.t('Share')}</th>
								<th class="whitespace-nowrap px-3 py-2.5 text-right font-medium">
									<button
										class="hover:text-gray-900 dark:hover:text-white {sortKey === 'cost_micros'
											? 'text-gray-900 dark:text-white'
											: ''}"
										on:click={() => (sortKey = 'cost_micros')}
									>
										{$i18n.t('Estimated spend')}
									</button>
								</th>
								<th class="whitespace-nowrap px-4 py-2.5 text-right font-medium">
									<button
										class="hover:text-gray-900 dark:hover:text-white {sortKey === 'updated_at'
											? 'text-gray-900 dark:text-white'
											: ''}"
										on:click={() => (sortKey = 'updated_at')}
									>
										{$i18n.t('Updated')}
									</button>
								</th>
							</tr>
						</thead>
						<tbody>
							{#if sortedUsers.length === 0}
								<tr>
									<td colspan="8" class="px-4 py-10 text-center text-gray-400">
										{$i18n.t('No usage yet')}
									</td>
								</tr>
							{:else}
								{#each sortedUsers as row (row.user_id)}
									<tr
										class="cursor-pointer border-t border-gray-100 hover:bg-gray-50/80 dark:border-gray-850 dark:hover:bg-gray-900/60"
										on:click={() => (openUserId = openUserId === row.user_id ? null : row.user_id)}
									>
										<td class="px-4 py-2.5">
											<div class="font-medium">{row.user_name || row.user_email || row.user_id}</div>
											{#if row.user_email && row.user_name}
												<div class="text-xs text-gray-500">{row.user_email}</div>
											{/if}
										</td>
										<td class="px-3 py-2.5 text-right tabular-nums">{formatTokens(row.request_count)}</td>
										<td class="px-3 py-2.5 text-right tabular-nums text-gray-500">{formatTokens(row.prompt_tokens)}</td>
										<td class="px-3 py-2.5 text-right tabular-nums text-gray-500">{formatTokens(row.completion_tokens)}</td>
										<td class="px-3 py-2.5 text-right font-medium tabular-nums">{formatTokens(row.total_tokens)}</td>
										<td class="px-3 py-2.5">
											<div class="flex items-center justify-end gap-2">
												<div class="h-1.5 w-14 overflow-hidden rounded-full bg-gray-100 dark:bg-gray-800">
													<div
														class="h-full rounded-full bg-gray-800 dark:bg-gray-200"
														style="width: {Math.min(share(row.total_tokens), 100)}%"
													></div>
												</div>
												<span class="w-8 text-right text-xs tabular-nums text-gray-500">{share(row.total_tokens)}%</span>
											</div>
										</td>
										<td class="px-3 py-2.5 text-right tabular-nums">
											{formatMoney(row.cost_micros)}
											{#if row.unpriced_tokens > 0}
												<div class="text-[11px] text-gray-400">
													{formatTokens(row.unpriced_tokens)} {$i18n.t('unpriced')}
												</div>
											{/if}
										</td>
										<td class="px-4 py-2.5 text-right text-xs text-gray-500">{formatUpdated(row.updated_at)}</td>
									</tr>
									{#if openUserId === row.user_id}
										<tr class="border-t border-gray-100 bg-gray-50 dark:border-gray-850 dark:bg-gray-900">
											<td colspan="8" class="px-4 py-3">
												{#if modelsFor(row.user_id).length === 0}
													<div class="text-xs text-gray-500">
														{$i18n.t('No model split yet. It appears after this user sends another request.')}
													</div>
												{:else}
													<div class="overflow-hidden rounded-xl border border-gray-100 bg-white dark:border-gray-850 dark:bg-gray-950">
														<table class="min-w-full text-xs">
															<thead class="text-gray-400">
																<tr>
																	<th class="px-3 py-2 text-left font-medium">{$i18n.t('Model')}</th>
																	<th class="px-3 py-2 text-left font-medium">{$i18n.t('Base model')}</th>
																	<th class="px-3 py-2 text-right font-medium">{$i18n.t('Input')}</th>
																	<th class="px-3 py-2 text-right font-medium">{$i18n.t('Output')}</th>
																	<th class="px-3 py-2 text-right font-medium">{$i18n.t('Total tokens')}</th>
																	<th class="px-3 py-2 text-right font-medium">{$i18n.t('Estimated spend')}</th>
																</tr>
															</thead>
															<tbody>
																{#each modelsFor(row.user_id) as model}
																	<tr class="border-t border-gray-100 dark:border-gray-850">
																		<td class="px-3 py-2">
																			<div>{model.model_name || model.model}</div>
																			{#if model.model_name}
																				<div class="font-mono text-[11px] text-gray-400">{model.model}</div>
																			{/if}
																		</td>
																		<td class="px-3 py-2 font-mono text-[11px] text-gray-500">
																			{model.base_model_id || '—'}
																		</td>
																		<td class="px-3 py-2 text-right tabular-nums">{formatTokens(model.prompt_tokens)}</td>
																		<td class="px-3 py-2 text-right tabular-nums">{formatTokens(model.completion_tokens)}</td>
																		<td class="px-3 py-2 text-right tabular-nums">{formatTokens(model.total_tokens)}</td>
																		<td class="px-3 py-2 text-right tabular-nums">{formatMoney(model.cost_micros)}</td>
																	</tr>
																{/each}
															</tbody>
														</table>
													</div>
												{/if}
											</td>
										</tr>
									{/if}
								{/each}
							{/if}
						</tbody>
					</table>
				</div>
			{/if}
		</div>
	{/if}
</div>
