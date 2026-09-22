import grpc

# GetInboundUsers returns a whole inbound's user list in one response; the
# default 4 MB receive cap is only tens of thousands of users.
_CHANNEL_OPTIONS = (("grpc.max_receive_message_length", 64 * 1024 * 1024),)


class XRayBase(object):
    def __init__(self, address: str, port: int, ssl_cert: str = None, ssl_target_name: str = None):
        if ssl_cert is None:
            self.address = address
            self.port = port
            self._channel = grpc.insecure_channel(f"{address}:{port}", options=_CHANNEL_OPTIONS)

        else:
            self.address = address
            self.port = port
            creds = grpc.ssl_channel_credentials(root_certificates=ssl_cert)
            opts = _CHANNEL_OPTIONS
            if ssl_target_name is not None:
                opts += (('grpc.ssl_target_name_override', ssl_target_name,),)
            self._channel = grpc.secure_channel(f"{address}:{port}",
                                                credentials=creds,
                                                options=opts)
