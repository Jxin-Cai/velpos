export function useCancelQuery(wsConnection) {
  function cancelQuery() {
    if (!wsConnection || wsConnection.getReadyState() !== WebSocket.OPEN) {
      return false
    }

    return wsConnection.send({ action: 'cancel' })
  }

  return { cancelQuery }
}
