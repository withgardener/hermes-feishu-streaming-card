def _deliver_result(job: dict, content: str, adapters=None, loop=None) -> Optional[str]:
    """
    Deliver job output to the configured target(s) (origin chat, specific platform, etc.).

    When ``adapters`` and ``loop`` are provided (gateway is running), tries to
    use the live adapter first — this supports E2EE rooms (e.g. Matrix) where
    the standalone HTTP path cannot encrypt.  Falls back to standalone send if
    the adapter path fails or is unavailable.

    Returns None on success, or an error string on failure.
    """
    targets = _resolve_delivery_targets(job)
    if not targets:
        deliver_value = _normalize_deliver_value(job.get("deliver", "local"))
        if deliver_value == "local":
            return None  # local-only jobs don't deliver — not a failure
        # deliver=origin with no resolvable origin and no configured home
        # channels: treat as local rather than reporting an error.  CLI-created
        # jobs never capture a {platform, chat_id} origin, so failing here would
        # make every CLI `deliver=origin` (or auto-detect) job emit a spurious
        # "no delivery target resolved" error on every run (#43014).  The output
        # is still persisted in last_output for `cron list`/resume.
        if deliver_value == "origin":
            logger.info(
                "Job '%s': deliver=origin but no origin or home channels — "
                "skipping delivery (output saved in last_output)",
                job.get("name", job.get("id", "?")),
            )
            return None
        msg = f"no delivery target resolved for deliver={deliver_value}"
        logger.warning("Job '%s': %s", job["id"], msg)
        return msg

    from tools.send_message_tool import _send_to_platform
    from gateway.config import load_gateway_config, Platform

    # Optionally wrap the content with a header/footer so the user knows this
    # is a cron delivery.  Wrapping is on by default; set cron.wrap_response: false
    # in config.yaml for clean output.
    wrap_response = True
    user_cfg = None
    try:
        user_cfg = load_config()
        wrap_response = user_cfg.get("cron", {}).get("wrap_response", True)
    except Exception:
        pass

    if wrap_response:
        task_name = job.get("name", job["id"])
        job_id = job.get("id", "")
        delivery_content = (
            f"Cronjob Response: {task_name}\n"
            f"(job_id: {job_id})\n"
            f"-------------\n\n"
            f"{content}\n\n"
            f"To stop or manage this job, send me a new message (e.g. \"stop reminder {task_name}\")."
        )
    else:
        delivery_content = content

    # Extract MEDIA: tags so attachments are forwarded as files, not raw text
    from gateway.platforms.base import BasePlatformAdapter
    media_files, cleaned_delivery_content = BasePlatformAdapter.extract_media(delivery_content)
    media_files = BasePlatformAdapter.filter_media_delivery_paths(media_files)

    # Resolve the delivery-mirror gate ONCE (default off). When on, each
    # successful delivery is also appended to the target chat's gateway session
    # transcript so a user reply in that chat sees the cron output in context.
    # Mirror the CLEAN, unwrapped output (not the cron header/footer).
    try:
        mirror_enabled = _cron_mirror_delivery_enabled(job, user_cfg)
    except Exception:
        mirror_enabled = False
    mirror_text = ""
    if mirror_enabled:
        _, mirror_text = BasePlatformAdapter.extract_media(content)
        mirror_text = (mirror_text or "").strip()

    try:
        config = load_gateway_config()
    except Exception as e:
        msg = f"failed to load gateway config: {e}"
        logger.error("Job '%s': %s", job["id"], msg)
        return msg

    delivery_errors = []

    for target in targets:
        platform_name = target["platform"]
        chat_id = target["chat_id"]
        thread_id = target.get("thread_id")

        # Diagnostic: log thread_id for topic-aware delivery debugging
        origin = _resolve_origin(job) or {}
        origin_thread = origin.get("thread_id")
        if origin_thread and not thread_id:
            logger.warning(
                "Job '%s': origin has thread_id=%s but delivery target lost it "
                "(deliver=%s, target=%s)",
                job["id"], origin_thread, job.get("deliver", "local"), target,
            )
        elif thread_id:
            logger.debug(
                "Job '%s': delivering to %s:%s thread_id=%s",
                job["id"], platform_name, chat_id, thread_id,
            )

        # Mirror is scoped to the ORIGIN conversation only. A fan-out / broadcast
        # / home-channel-fallback target is never mirrored (it is not the
        # conversation the job was created in, and may have no session at all).
        mirror_this_target = mirror_enabled and _target_matches_origin(
            origin, platform_name, chat_id, thread_id
        )
        # Pass the origin's user_id so a per-user-isolated group chat resolves to
        # the exact member who scheduled the job — parity with send_message.
        origin_user_id = origin.get("user_id") if mirror_this_target else None

        # Built-in names resolve to their enum member; plugin platform names
        # create dynamic members via Platform._missing_().
        try:
            platform = Platform(platform_name.lower())
        except (ValueError, KeyError):
            msg = f"unknown platform '{platform_name}'"
            logger.warning("Job '%s': %s", job["id"], msg)
            delivery_errors.append(msg)
            continue

        from gateway.delivery import resolve_delivery_transport

        transport = resolve_delivery_transport(platform, config, adapters)
        if transport is not None:
            pconfig = transport.config
            runtime_adapter = transport.adapter
        else:
            # No live transport: preserve the existing standalone delivery path,
            # which uses the logical platform's configured credential.
            pconfig = config.platforms.get(platform)
            runtime_adapter = None

        if not pconfig or not pconfig.enabled:
            msg = f"platform '{platform_name}' not configured/enabled"
            logger.warning("Job '%s': %s", job["id"], msg)
            delivery_errors.append(msg)
            continue

        # Prefer the resolved live transport when the gateway is running. This
        # supports E2EE native adapters and relay-fronted logical platforms.
        # The live-send path (which SEEDS the flat in_channel continuation
        # session via _seed_cron_channel_session) needs not just a live adapter
        # but a running event loop to schedule the async send onto. Compute that
        # gate ONCE so the in_channel thread_id clear below stays in lockstep
        # with the live-send/seed block further down (they used to drift): an
        # adapter can be present while the loop is absent/not-running, in which
        # case the live-send block is skipped and delivery falls through to the
        # standalone path — which cannot seed the flat session (r3609147550).
        live_adapter_ready = (
            runtime_adapter is not None
            and loop is not None
            and getattr(loop, "is_running", lambda: False)()
        )
        delivered = False
        target_errors = []

        # Continuable cron surface (D1/D2/D6): resolve the delivery surface for
        # this platform generically from its config ``extra``. Default "thread"
        # (today's behaviour, byte-identical). "in_channel" delivers the brief
        # FLAT into the channel (no dedicated thread) so a plain channel reply
        # continues the job in-context via the shared-channel session
        # ``(platform, chat_id, None)`` — the same bucket ``reply_in_thread:
        # false`` routes inbound channel messages to. The key is read
        # generically here (any platform); the ``in_channel`` branch is gated on
        # the adapter capability flag ``supports_inchannel_continuable`` so an
        # unsupported platform fails SAFE to "thread" (Slack is the first
        # consumer; "first consumer ≠ definition").
        surface_mode = "thread"
        try:
            surface_raw = (pconfig.extra or {}).get("cron_continuable_surface")
            if surface_raw is not None and str(surface_raw).strip().lower() == "in_channel":
                surface_mode = "in_channel"
        except Exception:
            surface_mode = "thread"
        in_channel_surface = surface_mode == "in_channel"
        if in_channel_surface and runtime_adapter is not None and not getattr(
            runtime_adapter, "supports_inchannel_continuable", False
        ):
            # Fail safe (D6): platform has no in_channel continuation primitive.
            logger.debug(
                "Job '%s': cron_continuable_surface=in_channel not supported on "
                "%s, using thread",
                job.get("id", "?"), platform_name,
            )
            in_channel_surface = False

        if in_channel_surface and mirror_this_target and live_adapter_ready:
            # Force flat delivery (D2): the continuable-channel target must
            # ignore any inherited origin/target thread_id, or the flat
            # continuable session seeded below (thread_id=None, via
            # _seed_cron_channel_session) never matches where the brief is
            # actually delivered — route_thread_id further down in this loop
            # reads `thread_id` and would otherwise route into the origin
            # thread instead of flat into the channel.
            #
            # Gated on `live_adapter_ready` (adapter present AND a running loop)
            # so the clear fires ONLY on the live-send path that actually seeds
            # the flat session — the SAME condition as the live-send block
            # below. `runtime_adapter is not None` alone is broader than that
            # path: an adapter can be present while the event loop is absent or
            # not running, in which case the live-send/seed block is skipped and
            # delivery falls through to the standalone path. Clearing thread_id
            # there would flatten a brief into a channel with NO seeded
            # continuable session behind it (and bypass the D6 capability
            # check), so the standalone fallback must keep the origin thread
            # (review r3609147550).
            #
            # Fan-out / broadcast / explicit-thread targets keep their thread_id
            # (they are not continuable and are never seeded). Placed AFTER
            # mirror_this_target / origin_user_id are computed above — those
            # need the ORIGINAL thread_id to match the origin conversation.
            thread_id = None

        # For an in_channel delivery the flat continuation session is created
        # explicitly below (the shipped mirror only APPENDS to an existing
        # session, and the flat channel row is otherwise absent for a
        # chat_postMessage delivery). ``is_dm`` selects the session chat_type so
        # the seeded key matches the inbound reply's key: a 1:1 DM keys as
        # ``dm`` (Slack DM channel ids start with "D"; or the origin says so),
        # everything else as ``group`` (shared channel). ``inchannel_seeded``
        # suppresses the generic mirror below so the brief is not double-written.
        origin_chat_type = str(origin.get("chat_type") or "").lower()
        is_dm_target = origin_chat_type == "dm" or (
            not origin_chat_type and str(chat_id).startswith("D")
        )
        inchannel_seeded = False

        # Continuable cron (thread-preferred): when mirroring is enabled for the
        # origin target and the gateway is live, try to open a DEDICATED thread
        # for this job and deliver the brief into it. On thread-capable
        # platforms (Telegram/Discord/Slack) the brief + the user's replies live
        # in their own scrollback; the thread-keyed session is seeded so a reply
        # continues with full context. On DM-only platforms (WhatsApp/Signal)
        # create_handoff_thread returns None and we fall back to mirroring into
        # the origin DM session (handled after delivery). Cf. _process_handoff.
        #
        # in_channel surface (D2): SKIP thread creation entirely — leave
        # thread_id=None so the delivery posts flat, then
        # ``_seed_cron_channel_session`` (below) CREATES the shared-channel
        # session and mirrors the brief into it. The shipped mirror alone is
        # NOT enough here: ``mirror_to_session`` only APPENDS to an existing
        # session and a flat ``(platform, chat_id, None)`` row is otherwise
        # absent for a ``chat_postMessage`` delivery, so the seed must create
        # the row first (F5).
        thread_seeded = False
        opened_thread_id: Optional[str] = None
        if (
            mirror_this_target
            and not in_channel_surface
            and runtime_adapter is not None
            and loop is not None
            and not thread_id  # never override an explicit origin thread/topic
        ):
            new_thread_id = _open_continuable_cron_thread(
                job, runtime_adapter, chat_id, loop,
            )
            if new_thread_id:
                # Route THIS delivery into the new thread now (the send needs the
                # thread_id), but defer seeding the thread session until the
                # delivery actually succeeds — otherwise an open-succeeds /
                # deliver-fails case leaves a seeded brief the user never saw,
                # and (worse) suppresses the DM-fallback mirror via thread_seeded.
                thread_id = new_thread_id
                opened_thread_id = new_thread_id

        if live_adapter_ready:
            # Telegram topic routing (#22773, regression fixed #52060): a
            # ``telegram:<positive_chat_id>:<numeric_thread_id>`` cron target is
            # ambiguous — a forum-style topic in a private chat and a genuine
            # Bot API channel Direct-Messages topic share the same shape and
            # need OPPOSITE routing. Disambiguate at delivery time via
            # ``_is_channel_dm_topic`` (see its docstring for the full
            # rationale); ``thread_id`` goes in ``route_metadata`` so the
            # anchorless cron send bypasses the DeliveryRouter's private-chat
            # reply-anchor requirement. Compute the routed metadata ONCE so both
            # the text send (via DeliveryRouter) and the media send agree.
            from gateway.delivery import (
                DeliveryRouter,
                DeliveryTarget,
                _looks_like_int,
                looks_like_telegram_private_chat_id,
            )

            is_ambiguous_telegram_topic = (
                platform == Platform.TELEGRAM
                and thread_id is not None
                and looks_like_telegram_private_chat_id(str(chat_id))
                and _looks_like_int(str(thread_id))
            )
            route_via_dm_topic = is_ambiguous_telegram_topic and _is_channel_dm_topic(
                runtime_adapter, chat_id, loop, job["id"],
            )
            if route_via_dm_topic:
                # Genuine Bot API channel Direct-Messages topic (#22773 mode 2):
                # routed via direct_messages_topic_id, no bare thread_id.
                route_thread_id = None
                route_metadata = {
                    "direct_messages_topic_id": str(thread_id),
                    "job_id": job["id"],
                }
                # Media metadata mirrors the text routing so attachments land in
                # the same DM topic instead of the General lane (#22773).
                media_metadata = {"direct_messages_topic_id": str(thread_id)}
            else:
                # Forum-style topic (private chat / supergroup) or non-topic
                # target: route via message_thread_id (#52060).  Put thread_id in
                # *route_metadata* (not just the DeliveryTarget) deliberately —
                # the DeliveryRouter's private-chat topic detection
                # (gateway/delivery.py) demands a reply anchor when thread_id is
                # absent from metadata; cron deliveries have no inbound reply
                # anchor, so the metadata key bypasses that check and lets the
                # adapter route via a plain message_thread_id.
                route_thread_id = str(thread_id) if thread_id is not None else None
                route_metadata = {"job_id": job["id"]}
                if route_thread_id:
                    route_metadata["thread_id"] = route_thread_id
                media_metadata = {"thread_id": thread_id} if thread_id else None

            try:
                # Send cleaned text (MEDIA tags stripped) — not the raw content.
                # Route through the gateway's DeliveryRouter so the live send
                # gets the same platform-specific routing as live messages —
                # in particular Telegram's three-mode topic routing.  The
                # standalone cron path lacked this, so DM-topic cron deliveries
                # landed in the General topic or were rejected by Bot API 10.0
                # (#22773).
                text_to_send = cleaned_delivery_content.strip()
                adapter_ok = True
                timed_out = False
                if text_to_send:
                    from agent.async_utils import safe_schedule_threadsafe

                    router = DeliveryRouter(config, adapters)
                    route_target = DeliveryTarget(
                        platform=platform,
                        chat_id=str(chat_id),
                        thread_id=route_thread_id,
                        is_explicit=True,
                    )
                    # Pass thread routing via the target (not a bare metadata
                    # "thread_id"): the router only applies its Telegram DM-topic
                    # detection when "thread_id"/"message_thread_id" are absent
                    # from metadata, deriving the routing from target.thread_id
                    # or the explicit direct_messages_topic_id above.
                    future = safe_schedule_threadsafe(
                        router._deliver_to_platform(
                            route_target,
                            text_to_send,
                            route_metadata,
                        ),
                        loop,
                    )
                    if future is None:
                        adapter_ok = False
                        target_errors.append("live adapter event loop scheduling failed")
                    else:
                        send_result = None
                        timeout_handled = False
                        try:
                            send_result = future.result(timeout=60)
                        except TimeoutError:
                            # #38922: a slow confirmation does NOT necessarily
                            # mean the send failed — but we must distinguish two
                            # cases via future.cancel()'s return value:
                            #
                            #   cancel() == False -> the coroutine was already
                            #     running on the gateway loop when the timeout
                            #     fired; the request is in flight on the wire and
                            #     cannot be un-sent.  Re-sending via standalone
                            #     would be a guaranteed DUPLICATE, so treat it as
                            #     delivered (assume-delivered).
                            #
                            #   cancel() == True -> the scheduled callback never
                            #     started executing (loop wedged/backlogged for
                            #     the full 60s), so nothing was sent.  We MUST
                            #     fall through to the standalone path or the
                            #     message is silently dropped (worse than a
                            #     duplicate).
                            cancelled = future.cancel()
                            if cancelled:
                                msg = (
                                    f"live adapter send to {platform_name}:{chat_id} "
                                    "timed out before the coroutine was dispatched"
                                )
                                logger.warning(
                                    "Job '%s': %s, falling back to standalone",
                                    job["id"], msg,
                                )
                                target_errors.append(msg)
                                adapter_ok = False  # fall through to standalone path
                                timeout_handled = True
                            else:
                                timed_out = True
                                timeout_handled = True
                                logger.warning(
                                    "Job '%s': live adapter send to %s:%s timed out "
                                    "after 60s; already dispatched (in flight), "
                                    "assuming delivered (skipping standalone fallback "
                                    "to avoid duplicate)",
                                    job["id"], platform_name, chat_id,
                                )
                        except Exception as ex:
                            # A real send error (not a slow confirmation) — fall
                            # through to the standalone path so the message is
                            # still delivered.
                            target_errors.append(f"live adapter send failed: {ex}")
                            raise

                        if timeout_handled:
                            # The timeout branch above already decided the
                            # outcome (assume-delivered if in flight, or
                            # adapter_ok=False to fall through if never
                            # dispatched).  send_result is None, so skip the
                            # confirmation/thread-fallback inspection below.
                            pass
                        else:
                            # _deliver_to_platform returns either a SendResult
                            # (.success attr) or, when the silence-narration
                            # filter drops the message, a plain dict
                            # {"success": True, "delivered": False, ...}.
                            # Normalize both shapes so a getattr default doesn't
                            # misread a dict, and so a None / success-less object
                            # is NOT counted as delivered (#47056).
                            if isinstance(send_result, dict):
                                send_success = bool(send_result.get("success", False))
                                send_raw_response = send_result.get("raw_response")
                            else:
                                send_success = _confirm_adapter_delivery(send_result)
                                send_raw_response = getattr(send_result, "raw_response", None)

                            if not send_success:
                                if isinstance(send_result, dict):
                                    err = send_result.get("error", "unknown")
                                    shape = "dict"
                                elif send_result is not None:
                                    err = getattr(send_result, "error", None)
                                    shape = type(send_result).__name__
                                else:
                                    err = "no response from adapter"
                                    shape = "None"
                                msg = (
                                    f"live adapter send to {platform_name}:{chat_id} "
                                    f"returned unconfirmed result ({shape}, error={err})"
                                )
                                if transport is not None and transport.is_relay:
                                    logger.warning("Job '%s': %s", job["id"], msg)
                                else:
                                    logger.warning(
                                        "Job '%s': %s, falling back to standalone",
                                        job["id"], msg,
                                    )
                                target_errors.append(msg)
                                adapter_ok = False  # fall through to standalone path
                            elif (
                                send_raw_response
                                and thread_id
                                and send_raw_response.get("thread_fallback")
                            ):
                                requested_thread_id = send_raw_response.get("requested_thread_id") or thread_id
                                msg = (
                                    f"configured thread_id {requested_thread_id} for "
                                    f"{platform_name}:{chat_id} was not found; delivered without thread_id"
                                )
                                logger.warning("Job '%s': %s", job["id"], msg)
                                delivery_errors.append(msg)

                # Send extracted media files as native attachments via the live
                # adapter, using the same DM-topic-aware routing as the text send
                # (#22773 — media previously used a bare thread_id and landed in
                # the General lane for private DM topics).  Skip on an in-flight
                # confirmation timeout: the gateway loop is contended, so each
                # media send would also block its 30s budget, and the text
                # payload is already assumed delivered (#38922).  Record the
                # skipped attachments so the drop is visible rather than silently
                # lost.
                if adapter_ok and not timed_out and media_files:
                    routed_media_metadata = dict(media_metadata or {})
                    if transport is not None and transport.is_relay:
                        routed_media_metadata["_relay_logical_platform"] = platform.value
                        logical_home = config.get_home_channel(platform)
                        if logical_home is not None and logical_home.chat_id == chat_id:
                            if logical_home.user_id:
                                routed_media_metadata["user_id"] = logical_home.user_id
                            if logical_home.scope_id:
                                routed_media_metadata["scope_id"] = logical_home.scope_id
                    _send_media_via_adapter(
                        runtime_adapter,
                        chat_id,
                        media_files,
                        routed_media_metadata or None,
                        loop,
                        job,
                        platform=platform,
                    )
                elif timed_out and media_files:
                    msg = (
                        f"{len(media_files)} media attachment(s) not delivered to "
                        f"{platform_name}:{chat_id} (live adapter confirmation timed out)"
                    )
                    logger.warning("Job '%s': %s", job["id"], msg)
                    delivery_errors.append(msg)

                if adapter_ok:
                    logger.info("Job '%s': delivered to %s:%s via live adapter", job["id"], platform_name, chat_id)
                    delivered = True
                    # Seed the thread session only now that delivery into it
                    # succeeded (deferred from thread-open above).
                    if opened_thread_id and not thread_seeded:
                        _seed_cron_thread_session(
                            job, runtime_adapter, platform_name, chat_id,
                            opened_thread_id, mirror_text,
                            chat_name=origin.get("chat_name"),
                        )
                        thread_seeded = True
                    # in_channel surface: CREATE + seed the flat channel/DM
                    # session (the shipped mirror only appends to an existing
                    # session — the flat row is otherwise absent for a
                    # chat_postMessage delivery, so the brief would be lost).
                    if in_channel_surface and mirror_this_target and not thread_seeded:
                        inchannel_seeded = _seed_cron_channel_session(
                            job, runtime_adapter, platform_name, chat_id,
                            mirror_text, is_dm=is_dm_target,
                            user_id=origin_user_id,
                            chat_name=origin.get("chat_name"),
                        )
                    _maybe_mirror_cron_delivery(
                        job, platform_name, chat_id, mirror_text,
                        thread_id=thread_id, user_id=origin_user_id,
                        enabled=mirror_this_target and not thread_seeded and not inchannel_seeded,
                    )
            except Exception as e:
                err_msg = f"live adapter delivery to {platform_name}:{chat_id} failed: {e}"
                if not any(err_msg in err for err in target_errors):
                    target_errors.append(err_msg)
                if transport is not None and transport.is_relay:
                    logger.warning("Job '%s': %s", job["id"], err_msg)
                else:
                    logger.warning(
                        "Job '%s': %s, falling back to standalone",
                        job["id"], err_msg,
                    )

        if not delivered:
            if transport is not None and transport.is_relay:
                # Relay owns the logical destination and its connector owns the
                # platform credential. A native retry could duplicate delivery
                # and cannot be authenticated correctly, so fail closed.
                if not target_errors:
                    target_errors.append(
                        f"relay delivery to {platform_name}:{chat_id} failed"
                    )
                delivery_errors.extend(target_errors)
                continue
            # If the interpreter is finalizing (gateway SIGTERM / restart /
            # OOM), scheduling any new delivery is futile — asyncio.run and a
            # fresh ThreadPoolExecutor both raise "cannot schedule new futures
            # after interpreter shutdown". Skip gracefully with a warning
            # rather than emitting an ERROR traceback on every restart-race
            # (#58720, #55924).
            if _interpreter_shutting_down():
                msg = f"delivery to {platform_name}:{chat_id} skipped — interpreter is shutting down"
                logger.warning("Job '%s': %s", job["id"], msg)
                target_errors.append(msg)
                delivery_errors.extend(target_errors)
                continue
            # Standalone path: run the async send in a fresh event loop (safe from any thread)
            coro = _send_to_platform(platform, pconfig, chat_id, cleaned_delivery_content, thread_id=thread_id, media_files=media_files)
            try:
                result = asyncio.run(coro)
            except RuntimeError as run_err:
                # asyncio.run() checks for a running loop before awaiting the coroutine;
                # when it raises, the original coro was never started — close it to
                # prevent "coroutine was never awaited" RuntimeWarning, then retry in a
                # fresh thread that has no running loop.
                coro.close()
                # If the RuntimeError is the interpreter-finalization signal,
                # the fresh-thread fallback would fail identically — skip
                # gracefully instead of logging a shutdown-race traceback.
                if _interpreter_shutting_down(run_err):
                    msg = f"delivery to {platform_name}:{chat_id} skipped — interpreter is shutting down"
                    logger.warning("Job '%s': %s", job["id"], msg)
                    target_errors.append(msg)
                    delivery_errors.extend(target_errors)
                    continue
                # The thread-pool fallback can itself raise (SMTP ConnectionError,
                # future.result timeout, etc.). An exception raised inside this
                # `except RuntimeError` block is NOT caught by the sibling
                # `except Exception` below — it would escape _deliver_result()
                # and crash the whole delivery loop, silently skipping every
                # remaining target (#47163). Wrap the fallback in its own
                # try/except so a per-target failure is logged and the loop
                # continues to the next target.
                try:
                    pool = concurrent.futures.ThreadPoolExecutor(max_workers=1)
                    try:
                        future = pool.submit(asyncio.run, _send_to_platform(platform, pconfig, chat_id, cleaned_delivery_content, thread_id=thread_id, media_files=media_files))
                        result = future.result(timeout=30)
                    finally:
                        pool.shutdown(wait=False)
                except Exception as e:
                    # A shutdown-race here is expected during teardown; downgrade
                    # to a warning so it doesn't read as a genuine failure.
                    if _interpreter_shutting_down(e):
                        msg = f"delivery to {platform_name}:{chat_id} skipped — interpreter is shutting down"
                        logger.warning("Job '%s': %s", job["id"], msg)
                        target_errors.append(msg)
                        delivery_errors.extend(target_errors)
                        continue
                    msg = f"delivery to {platform_name}:{chat_id} failed: {e}"
                    logger.error("Job '%s': %s", job["id"], msg, exc_info=True)
                    target_errors.extend([msg])
                    delivery_errors.extend(target_errors)
                    continue
            except Exception as e:
                msg = f"delivery to {platform_name}:{chat_id} failed: {e}"
                logger.error("Job '%s': %s", job["id"], msg, exc_info=True)
                target_errors.extend([msg])
                delivery_errors.extend(target_errors)
                continue

            if result and result.get("error"):
                msg = f"delivery error: {result['error']}"
                logger.error("Job '%s': %s", job["id"], msg)
                target_errors.extend([msg])
                delivery_errors.extend(target_errors)
                continue

            logger.info("Job '%s': delivered to %s:%s", job["id"], platform_name, chat_id)
            _maybe_mirror_cron_delivery(
                job, platform_name, chat_id, mirror_text,
                thread_id=thread_id, user_id=origin_user_id,
                enabled=mirror_this_target and not thread_seeded,
            )

    if delivery_errors:
        return "; ".join(delivery_errors)
    return None
