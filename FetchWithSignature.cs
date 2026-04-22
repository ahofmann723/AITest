using System;
using System.Net.Http;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Threading.Tasks;

public static class SignedClient
{
    private const string Key = "Insert your API Key here";
    private const string Secret = "Insert your API secret here";
    private const string Url = "Insert the target URL here";

    private static readonly HttpClient Http = new HttpClient();

    public static Task<HttpResponseMessage> FetchWithSignatureAsync(
        string apiKey, string secretKey, HttpMethod method, object body)
    {
        var clientRequestId = Guid.NewGuid().ToString();
        var time = DateTimeOffset.UtcNow.ToUnixTimeMilliseconds();
        var requestBody = JsonSerializer.Serialize(body);

        var messageSignatureString = apiKey + clientRequestId + time + requestBody;

        string messageSignatureBase64;
        using (var hmac = new HMACSHA256(Encoding.UTF8.GetBytes(secretKey)))
        {
            var hash = hmac.ComputeHash(Encoding.UTF8.GetBytes(messageSignatureString));
            messageSignatureBase64 = Convert.ToBase64String(hash);
        }

        var request = new HttpRequestMessage(method, Url);
        request.Headers.Add("Client-Request-Id", clientRequestId);
        request.Headers.Add("Api-Key", apiKey);
        request.Headers.Add("Timestamp", time.ToString());
        request.Headers.Add("Message-Signature", messageSignatureBase64);

        if (method != HttpMethod.Get)
        {
            request.Content = new StringContent(requestBody, Encoding.UTF8, "application/json");
        }

        return Http.SendAsync(request);
    }

    // example call
    public static async Task Main()
    {
        try
        {
            var response = await FetchWithSignatureAsync(
                Key, Secret, HttpMethod.Post, new { /* Request body */ });
            // success!
        }
        catch (Exception)
        {
            // failed!
        }
    }
}
