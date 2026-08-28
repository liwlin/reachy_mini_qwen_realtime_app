(function exposeLocalVideo(root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) {
    module.exports = api;
    return;
  }
  root.ReachyLocalVideo = api.ReachyLocalVideo;
})(typeof globalThis !== "undefined" ? globalThis : window, function buildLocalVideo() {
  "use strict";

  const LISTENER_STATUS = {
    type: "setPeerStatus",
    roles: ["listener"],
    meta: { name: "local-mobile-control" },
  };

  class ReachyLocalVideo {
    constructor(options) {
      this.hostname = options.hostname;
      this.video = options.video;
      this.onState = options.onState || (() => {});
      this.WebSocketCtor = options.WebSocketCtor || globalThis.WebSocket;
      this.RTCPeerConnectionCtor = options.RTCPeerConnectionCtor || globalThis.RTCPeerConnection;
      this.MediaStreamCtor = options.MediaStreamCtor || globalThis.MediaStream;
      this.setTimer = options.setTimer || globalThis.setTimeout.bind(globalThis);
      this.clearTimer = options.clearTimer || globalThis.clearTimeout.bind(globalThis);
      this.state = "stopped";
      this.socket = null;
      this.peer = null;
      this.remoteStream = null;
      this.sessionId = null;
      this.pendingRemoteIce = [];
      this.retryTimer = null;
      this.retryDelay = 1000;
      this.manualStopped = true;
      this.hasVideo = false;
      this.iceConnected = false;
    }

    connect() {
      if (!this.manualStopped && this.socket) return;
      this.manualStopped = false;
      this.retryDelay = 1000;
      this._openSocket();
    }

    disconnect() {
      this.manualStopped = true;
      this._cancelRetry();
      this._sendEndSession();
      this._closeTransport(true);
      this._setState("stopped");
    }

    _setState(state, detail = "") {
      this.state = state;
      this.onState(state, detail);
    }

    _openSocket() {
      if (this.manualStopped) return;
      this._closeTransport(false);
      this._setState("connecting");
      const socket = new this.WebSocketCtor(`ws://${this.hostname}:8443`);
      this.socket = socket;
      socket.onopen = () => {
        if (this.socket !== socket || this.manualStopped) return;
        this._setState("signalling");
      };
      socket.onmessage = (event) => {
        void this._handleMessage(event.data).catch(() => this._scheduleReconnect("signalling_error"));
      };
      socket.onerror = () => {
        if (this.socket === socket && !this.manualStopped) this._setState("unavailable", "socket_error");
      };
      socket.onclose = () => {
        if (this.socket === socket && !this.manualStopped) this._scheduleReconnect("socket_closed");
      };
    }

    async _handleMessage(raw) {
      let message;
      try {
        message = JSON.parse(raw);
      } catch (_failure) {
        return;
      }
      if (!message || typeof message !== "object") return;

      if (message.type === "welcome") {
        this._send(LISTENER_STATUS);
        this._send({ type: "list" });
        return;
      }
      if (message.type === "list") {
        const producers = Array.isArray(message.producers) ? message.producers : [];
        const producer = producers.find((item) => item?.meta?.name === "reachymini") || producers[0];
        if (!producer || typeof producer.id !== "string") {
          this._setState("unavailable", "producer_not_found");
          return;
        }
        this._ensurePeer();
        this._send({ type: "startSession", peerId: producer.id });
        return;
      }
      if (message.type === "sessionStarted" && typeof message.sessionId === "string") {
        this.sessionId = message.sessionId;
        return;
      }
      if (message.type === "endSession") {
        this._scheduleReconnect("session_ended");
        return;
      }
      if (message.type !== "peer") return;
      if (typeof message.sessionId === "string" && !this.sessionId) this.sessionId = message.sessionId;
      if (message.sdp) await this._answerOffer(message.sdp);
      if (message.ice) await this._acceptRemoteIce(message.ice);
    }

    _ensurePeer() {
      if (this.peer) return this.peer;
      const peer = new this.RTCPeerConnectionCtor({ iceServers: [] });
      this.peer = peer;
      peer.onicecandidate = (event) => {
        if (!event.candidate || !this.sessionId) return;
        const candidate = typeof event.candidate.toJSON === "function" ? event.candidate.toJSON() : event.candidate;
        this._send({ type: "peer", sessionId: this.sessionId, ice: candidate });
      };
      peer.oniceconnectionstatechange = () => {
        const state = peer.iceConnectionState;
        if (state === "connected" || state === "completed") {
          this.iceConnected = true;
          this._markLive();
          return;
        }
        if (["disconnected", "failed"].includes(state) && !this.manualStopped) {
          this._scheduleReconnect(`ice_${state}`);
        }
      };
      peer.ontrack = (event) => this._acceptTrack(event.track);
      peer.ondatachannel = (event) => event.channel.close();
      return peer;
    }

    async _answerOffer(description) {
      const peer = this._ensurePeer();
      await peer.setRemoteDescription(description);
      for (const transceiver of peer.getTransceivers()) {
        const kind = transceiver.receiver?.track?.kind;
        try {
          transceiver.direction = kind === "video" ? "recvonly" : "inactive";
        } catch (_failure) {
          if (kind === "audio" && transceiver.receiver?.track) transceiver.receiver.track.enabled = false;
        }
      }
      for (const candidate of this.pendingRemoteIce.splice(0)) {
        await peer.addIceCandidate(candidate);
      }
      const answer = await peer.createAnswer();
      await peer.setLocalDescription(answer);
      if (this.sessionId) {
        this._send({ type: "peer", sessionId: this.sessionId, sdp: answer });
      }
    }

    async _acceptRemoteIce(candidate) {
      const peer = this._ensurePeer();
      if (!peer.remoteDescription) {
        this.pendingRemoteIce.push(candidate);
        return;
      }
      await peer.addIceCandidate(candidate);
    }

    _acceptTrack(track) {
      if (!track) return;
      if (track.kind === "audio") {
        track.enabled = false;
        return;
      }
      if (track.kind !== "video") return;
      if (this.remoteStream) this.remoteStream.getTracks().forEach((current) => current.stop());
      this.remoteStream = new this.MediaStreamCtor([track]);
      this.video.srcObject = this.remoteStream;
      this.hasVideo = true;
      const playback = this.video.play?.();
      if (playback && typeof playback.catch === "function") playback.catch(() => {});
      this._markLive();
    }

    _markLive() {
      if (!this.hasVideo || !this.iceConnected) return;
      this.retryDelay = 1000;
      this._setState("live");
    }

    _send(message) {
      if (!this.socket || this.socket.readyState !== 1) return false;
      this.socket.send(JSON.stringify(message));
      return true;
    }

    _sendEndSession() {
      if (this.sessionId) this._send({ type: "endSession", sessionId: this.sessionId });
    }

    _scheduleReconnect(reason) {
      if (this.manualStopped || this.retryTimer) return;
      this._closeTransport(false);
      const delay = Math.min(this.retryDelay, 10000);
      this.retryDelay = Math.min(delay * 2, 10000);
      this._setState("reconnecting", reason);
      let timer;
      const callback = () => {
        if (this.retryTimer !== timer || this.manualStopped) return;
        this.retryTimer = null;
        this._openSocket();
      };
      timer = this.setTimer(callback, delay);
      this.retryTimer = timer;
    }

    _cancelRetry() {
      if (!this.retryTimer) return;
      this.clearTimer(this.retryTimer);
      this.retryTimer = null;
    }

    _closeTransport(closeSocket) {
      const socket = this.socket;
      this.socket = null;
      if (socket) {
        socket.onopen = null;
        socket.onmessage = null;
        socket.onerror = null;
        socket.onclose = null;
        if (closeSocket && socket.readyState !== 3) socket.close();
      }
      if (this.peer) this.peer.close();
      this.peer = null;
      if (this.remoteStream) this.remoteStream.getTracks().forEach((track) => track.stop());
      this.remoteStream = null;
      this.video.srcObject = null;
      this.sessionId = null;
      this.pendingRemoteIce = [];
      this.hasVideo = false;
      this.iceConnected = false;
    }
  }

  return { ReachyLocalVideo };
});
